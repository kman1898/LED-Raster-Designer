"""NovaStar copy mode, mirror screens, the per-port card-or-box choice, and
the cards that cannot load one screen together (owner's rulings, 2026-10-30).

Every rule here is one NovaStar documents, for the product it names, and no
other product gains it by resemblance:

* H_4xfiber: "Independent, copy and backup modes are supported." Copy: "OPT 3
  copies the output on OPT 1, while OPT 4 copies the output on OPT 2". Backup:
  "OPT 3 serves as the backup of OPT 1, while OPT 4 serves as the backup of
  OPT 2." (H15 Video Wall Splicer Specifications V1.15.0 p.36; H2/H5 V1.17.0
  and H9 V1.16.0 the same.) A file saved with the old combined copy-backup mode
  opens as Backup, which is how it behaved.
* H_4xfiber (enhanced): "8x 10G OPT Ports", "OPT 1 to OPT 4 serve as the
  primary ports, and OPT 5 to OPT 8 serve as the backup ones", "OPT 5 backs up
  or copies the output on OPT 1", "Copy and backup modes are supported. Only
  the cards set in the same modes can be used together to load a screen."
  (H15 V1.15.0 p.37) - 8 trunks, 40 ports, no Independent.
* MX40 Pro, 20-port mode: "OPT 3 is the copy channel of OPT 1" (User Manual
  V1.5.0 p.9) - owner: "Either, you pick", a box there is Mirror or Backup.
  And "You can use the optical port alongside the physical Ethernet port" -
  each of ports 1-20 plugs in at the RJ45 or the box, per port.
* H_16xRJ45+2xfiber: OPT 1/2 copy Ethernet 1-8 / 9-16; the owner has used
  both on one card ("Yes, I've done it") - per port, card or box.
* "The fiber sending card cannot be used together with the H_20xRJ45 sending
  card or H_16xRJ45+2xfiber sending card to load the same screen" (H15
  V1.15.0 p.2), and the enhanced card "cannot be used together with the
  H_4xfiber sending card, H_20xRJ45 sending card or H_16xRJ45+2xfiber sending
  card to load the same screen" (p.37-38) - refused, never warned.
* Mirror a screen: "the copy screen's port map follows the first
  automatically and can't be drawn separately." Since 2026-11-01 (owner) it
  is made by dragging a card in Copy mode onto a second screen (the browser
  half is tests/test_copy_mode_ui.py; here the layer PUT the drop sends). The
  screens match on columns x rows, pixels per cabinet and port order (blank,
  hidden and half cabinets in the same places) - not on the panel's mm. A
  source unplugged from the copy-mode card takes its copy with it; a release
  of the copy alone just removes the copy.
"""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402
import port_assignment as assignment  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


H4 = 'novastar-card-h-4xfiber'
H4E = 'novastar-card-h-4xfiber-enhanced'
H20 = 'novastar-card-h-20xrj45'
H16 = 'novastar-card-h-16xrj45-2xfiber'
MX40 = 'novastar-mx40-pro'
CVT10 = 'novastar-cvt10'

# The units whose own documents name a copy or backup OPT, beyond the H
# cards, the MX40 Pro and the NovaPro UHDs, each with the field that quotes
# it and the words it must quote (2026-11-02, the owner: "Any processor that
# supports hot backup or copy will need to support this in our app").
COPY_SOURCES = {
    'novastar-vx400-pro': ('modesNote', ['Table 5-7 OPT working mode',
        'Backup: OPT 2 backs up the output on Ethernet ports 1~4.']),
    'novastar-vx600-pro': ('modesNote', ['Table 5-7 OPT working mode',
        'Backup: OPT 2 backs up the output on Ethernet ports 1~6.']),
    'novastar-vx1000-pro': ('modesNote', ['Table 5-7 OPT working mode',
        'Backup: OPT 2 backs up the output on Ethernet ports 1~10.']),
    'novastar-vx1000': ('modesNote', ['Specifications V1.6.0 (2024-07-08) p.7',
        'OPT | 2 | 10G optical fiber ports',
        'OPT 2: For output only, with copy and backup modes',
        'OPT 2 copies or backs up the output on 10 Ethernet ports.']),
    'novastar-vx2000-pro': ('modesNote', ['Table 5-7 OPT working mode',
        'You can set the working mode of OPT 3 and OPT 4 to Copy or Backup.']),
    'novastar-mctrl660-pro': ('copyTrunksNote', ['Specifications V1.4.1 p.4',
        'OPT2 is the backup input or output port of OPT1.']),
    'novastar-mctrl-r5': ('copyTrunksNote', ['Specifications V1.0.5 p.4',
        'OPT 2 is the copy channel of OPT 1.',
        'OPT2 serves as the backup for OPT1.']),
    'novastar-mctrl4k': ('copyTrunksNote', ['Specifications V1.2.1 p.4',
        'OPT3 is a duplicate channel of OPT1.',
        'OPT3 and OPT4 are backup input/output ports.']),
    'novastar-mx30': ('copyTrunksNote', ['Specifications V1.5.0 p.8',
        'OPT 2 is the copy channel of OPT 1.']),
    'novastar-mx20': ('copyTrunksNote', ['Specifications V1.5.1 p.6',
        'OPT 2 is the copy channel of OPT 1.']),
}


# ── helpers ───────────────────────────────────────────────────────────────

def _ok(resp, status=(200, 201)):
    assert resp.status_code in ((status,) if isinstance(status, int)
                                else status), resp.get_data(as_text=True)
    return resp.get_json()


def h9(client):
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}))
    return st['processors'][-1]['id']


def slot_card(client, pid, slot, device, mode=None):
    st = _ok(client.put(f'/api/processors/{pid}/slots/{slot}',
                        json={'deviceId': device}))
    cid = next(p for p in st['processors'] if p['id'] == pid
               )['slots'][slot]['card']['id']
    if mode:
        _ok(client.put(f'/api/processors/{pid}/cards/{cid}',
                       json={'mode': mode}))
    return cid


def add_boxes(client, pid, cid, n, **body):
    st = None
    for _ in range(n):
        st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                             json=dict({'deviceId': CVT10, 'pair': False},
                                       **body)))
    return st


def tree(client):
    return client.get('/api/processors').get_json()['resolved']


def card_of(client, cid):
    for proc in tree(client):
        for slot in proc['slots']:
            if slot['card'] and slot['card']['id'] == cid:
                return slot['card']
    raise AssertionError(f'no card {cid}')


def raw_card(client, cid):
    for proc in client.get('/api/processors').get_json()['processors']:
        for slot in proc['slots']:
            if slot['card'] and slot['card']['id'] == cid:
                return slot['card']
    raise AssertionError(f'no card {cid}')


def screen(client, name, columns=4, rows=3, **extra):
    body = dict({'name': name, 'columns': columns, 'rows': rows,
                 'cabinet_width': 128, 'cabinet_height': 128}, **extra)
    _ok(client.post('/api/layer/add', json=body), 200)
    return next(l for l in client.get('/api/project').get_json()['layers']
                if l['name'] == name)['id']


def resolve(client, screens):
    return _ok(client.post('/api/port-assignments/resolve',
                           json={'screens': screens}))['resolution']


def pin(client, screens, layer, index, cid, port, status=200):
    return client.post('/api/port-assignments/place', json={
        'screens': screens, 'layerId': str(layer), 'index': index,
        'cardId': cid, 'port': port})


def summary(res, cid):
    return next(c for c in res['cards'] if c['cardId'] == cid)


def scr_of(res, layer):
    return next(s for s in res['screens'] if s['layerId'] == str(layer))


# ── 1. the catalog: three modes, eight OPTs ───────────────────────────────

def test_h4xfiber_has_novastars_three_modes():
    """H15 V1.15.0 p.36: "Independent, copy and backup modes are
    supported." Copy and Backup are both 16 ports - OPT 1/2 main."""
    d = catalog.get_device(H4)
    modes = {m['id']: m for m in d['ports']['modes']}
    assert list(modes) == ['independent', 'copy', 'backup']
    assert [modes[k]['label'] for k in modes] == ['Independent', 'Copy',
                                                  'Backup']
    assert (modes['independent']['count'], modes['copy']['count'],
            modes['backup']['count']) == (32, 16, 16)
    assert catalog.copy_trunks(d, 'copy') == 'mirror'
    assert catalog.copy_trunks(d, 'backup') == 'backup'
    assert catalog.copy_trunks(d, 'independent') is None


def test_enhanced_is_eight_opts_of_ten_with_copy_and_backup_only():
    """H15 V1.15.0 p.37: "8x 10G OPT Ports", OPT 5-8 back up or copy OPT
    1-4, one OPT = 10 Ethernet ports, "Copy and backup modes are
    supported." 40 ports, never 80; no Independent."""
    d = catalog.get_device(H4E)
    assert (d['trunks'], d['portsPerTrunk'], d['trunkWord']) == (8, 10, 'OPT')
    assert [m['id'] for m in d['ports']['modes']] == ['copy', 'backup']
    assert d['ports']['defaultMode'] == 'backup'
    assert all(m['count'] == 40 for m in d['ports']['modes'])
    assert catalog.port_capacity(H4E)['count'] == 40


def test_old_mode_ids_read_as_the_mode_they_named():
    """copy-backup ran as Backup (OPT 3/4 backing OPT 1/2), and the
    enhanced card's one "default" mode was its Backup shape."""
    assert catalog.port_capacity(H4, 'copy-backup') == {
        'count': 16, 'known': True, 'mode': 'backup', 'reason': ''}
    assert catalog.port_capacity(H4E, 'default')['mode'] == 'backup'
    assert catalog.canonical_mode(catalog.get_device(H4), 'copy-backup') \
        == 'backup'
    # nothing is guessed for an id the catalog never had
    assert catalog.port_capacity(H4, 'nonsense')['count'] is None


def test_only_the_named_products_carry_the_new_rules():
    """No hardware assumption: copy trunks, the plug choice and the screen
    rules sit on the products NovaStar documents them for, and nowhere
    else in the catalog."""
    copy_devices = sorted(d['id'] for d in catalog.devices()
                          if any(m.get('copyTrunks') for m in
                                 (d.get('ports') or {}).get('modes') or []))
    # The NovaPro UHD and UHD Jr joined on 2026-11-02, each quoting its own
    # sheet's "copy/hot backup" channel (copyTrunksNote), and the same day
    # every other NovaStar unit whose own documents name a copy or backup
    # OPT (tests/test_copy_backup_all.py holds each quote).
    assert copy_devices == sorted([H4, H4E, MX40, 'novastar-novapro-uhd',
                                   'novastar-novapro-uhd-jr'] + list(COPY_SOURCES))
    # each quotes its source: a mode set per unit in modesNote, one fixed
    # role or a per-box choice in copyTrunksNote
    assert all(catalog.get_device(d).get('copyTrunksNote')
               or catalog.get_device(d).get('modesNote')
               for d in copy_devices)
    for unit, (field, words) in COPY_SOURCES.items():
        for w in words:
            assert w in catalog.get_device(unit)[field], (unit, w)
    assert sorted(d['id'] for d in catalog.devices() if d.get('plugChoice')) \
        == sorted([H16, MX40])
    assert sorted(d['id'] for d in catalog.devices()
                  if d.get('screenExcludes')) == sorted([H4, H4E, H16, H20])
    assert [d['id'] for d in catalog.devices() if d.get('screenSameMode')] \
        == [H4E]
    # The MX_4x10G documents no copy mode (MX2000 Pro / MX6000 Pro
    # specifications) and stays as it was.
    mx = catalog.get_device('novastar-card-mx-4x10g')
    assert [m['id'] for m in mx['ports']['modes']] == ['default']


# ── 2. the migration ──────────────────────────────────────────────────────

def test_saved_copy_backup_and_default_open_as_backup(client):
    pid = h9(client)
    h4 = slot_card(client, pid, 0, H4)
    h4e = slot_card(client, pid, 1, H4E)
    project = client.get('/api/project').get_json()
    for proc in project['processors']:
        for slot in proc['slots']:
            card = slot['card']
            if card and card['id'] == h4:
                card['mode'] = 'copy-backup'
            if card and card['id'] == h4e:
                card['mode'] = 'default'
    # both funnels: the restore (file open, undo) and the save
    _ok(client.put('/api/project', json=copy.deepcopy(project)), 200)
    assert raw_card(client, h4)['mode'] == 'backup'
    assert raw_card(client, h4e)['mode'] == 'backup'
    _ok(client.post('/api/project', json=copy.deepcopy(project)), 200)
    assert raw_card(client, h4)['mode'] == 'backup'
    assert raw_card(client, h4e)['mode'] == 'backup'
    assert card_of(client, h4)['ceiling'] == 0  # box-fed, no box yet
    # the card PUT takes the old id too, as the mode it named
    _ok(client.put(f'/api/processors/{pid}/cards/{h4}',
                   json={'mode': 'copy-backup'}))
    assert raw_card(client, h4)['mode'] == 'backup'


def test_migrate_card_modes_is_idempotent():
    project = {'processors': [{'id': 'p', 'slots': [
        {'index': 0, 'card': {'id': 'c1', 'deviceId': H4,
                              'mode': 'copy-backup'}},
        {'index': 1, 'card': {'id': 'c2', 'deviceId': H4E,
                              'mode': 'default'}},
        {'index': 2, 'card': {'id': 'c3', 'deviceId': H4,
                              'mode': 'independent'}}]}]}
    moved = catalog.migrate_card_modes(project)
    assert [(m['cardId'], m['to']) for m in moved] == [('c1', 'backup'),
                                                       ('c2', 'backup')]
    assert catalog.migrate_card_modes(project) == []


# ── 3. the numbering: copies that feed a mirror are sockets of their own ──

def test_copy_mode_numbers_the_mirror_boxes_past_the_count(client):
    pid = h9(client)
    cid = slot_card(client, pid, 0, H4, 'copy')
    add_boxes(client, pid, cid, 4)
    card = card_of(client, cid)
    boxes = card['cvts']
    assert [(b['trunkTitle'], b['firstPort'], b['portCount'], b['copyRole'])
            for b in boxes] == [('OPT 1', 1, 8, None), ('OPT 2', 9, 8, None),
                                ('OPT 3', 17, 8, 'mirror'),
                                ('OPT 4', 25, 8, 'mirror')]
    assert boxes[2]['mirrorOf'] == boxes[0]['id']
    assert boxes[3]['mirrorOf'] == boxes[1]['id']
    # 16 ports is still what the card has; the copies are not more of them
    assert (card['ceiling'], card['defined'], card['over']) == (16, 16, False)
    mirror = [p for p in card['ports'] if p['mirrorOf']]
    assert [p['number'] for p in mirror] == list(range(17, 33))
    assert [p['localNumber'] for p in mirror[:8]] == list(range(1, 9))
    assert mirror[0]['mirrorOf'] == 1 and mirror[8]['mirrorOf'] == 9
    assert card['mirrorSockets']['1'] == 17 and card['mirrorSockets']['16'] \
        == 32
    assert not any(p['beyondCeiling'] for p in card['ports'])


def test_backup_mode_keeps_the_copies_on_the_primary_numbers(client):
    """Backup is what copy-backup always did: OPT 3 delivers 1-8 again."""
    pid = h9(client)
    cid = slot_card(client, pid, 0, H4, 'backup')
    add_boxes(client, pid, cid, 4)
    card = card_of(client, cid)
    assert [(b['firstPort'], b['copyRole'], bool(b['duplicateOf']))
            for b in card['cvts']] == [(1, None, False), (9, None, False),
                                       (1, 'backup', True),
                                       (9, 'backup', True)]
    assert [p['number'] for p in card['ports']] == list(range(1, 17))
    assert card['mirrorSockets'] == {}


def test_enhanced_copy_and_backup_follow_opt_n_plus_four(client):
    pid = h9(client)
    cid = slot_card(client, pid, 0, H4E, 'copy')
    add_boxes(client, pid, cid, 8)
    card = card_of(client, cid)
    assert card['trunkTitles'] == [f'OPT {n}' for n in range(1, 9)]
    assert [b['firstPort'] for b in card['cvts']] \
        == [1, 11, 21, 31, 41, 51, 61, 71]
    assert [b['copyRole'] for b in card['cvts'][4:]] == ['mirror'] * 4
    assert card['ceiling'] == 40 and card['defined'] == 40
    assert card['mirrorSockets']['31'] == 71
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}',
                   json={'mode': 'backup'}))
    card = card_of(client, cid)
    assert [b['firstPort'] for b in card['cvts']] \
        == [1, 11, 21, 31, 1, 11, 21, 31]
    assert len(card['ports']) == 40 and card['ceiling'] == 40


def test_enhanced_without_boxes_on_5_to_8_is_what_it_always_was(client):
    """The default mode keeps saved files: 40 ports on OPT 1-4, nothing on
    OPT 5-8, no gap, no shortfall."""
    pid = h9(client)
    cid = slot_card(client, pid, 0, H4E)
    assert raw_card(client, cid)['mode'] == 'backup'
    add_boxes(client, pid, cid, 4)
    card = card_of(client, cid)
    assert [b['trunkTitle'] for b in card['cvts']] == ['OPT 1', 'OPT 2',
                                                       'OPT 3', 'OPT 4']
    assert (card['ceiling'], card['defined'], card['gaps'],
            card['shortfall'], card['trunksFree']) == (40, 40, [], None, 4)


def test_a_new_box_pairs_in_backup_and_stands_alone_in_copy(client):
    """NovaStar's default pair (default_backup_pair) is a backup default:
    in Copy the copy OPT feeds a mirror, so a box goes on alone."""
    pid = h9(client)
    cid = slot_card(client, pid, 0, H4E, 'backup')
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': CVT10}))
    card = card_of(client, cid)
    assert [b['trunkTitle'] for b in card['cvts']] == ['OPT 1', 'OPT 5']
    assert card['cvts'][1]['backupOf'] == card['cvts'][0]['id']
    cid2 = slot_card(client, pid, 1, H4, 'copy')
    _ok(client.post(f'/api/processors/{pid}/cards/{cid2}/cvts',
                    json={'deviceId': CVT10}))
    assert len(card_of(client, cid2)['cvts']) == 1
    assert st


# ── 4. MX40 Pro 20-port: Mirror or Backup, per box ────────────────────────

def mx40(client, mode='20-port'):
    st = _ok(client.post('/api/processors', json={'deviceId': MX40}))
    proc = st['processors'][-1]
    cid = proc['slots'][0]['card']['id']
    _ok(client.put(f'/api/processors/{proc["id"]}/cards/{cid}',
                   json={'mode': mode}))
    return proc['id'], cid


def test_mx40_pro_20_port_box_on_opt3_is_backup_unless_set_to_mirror(client):
    pid, cid = mx40(client)
    # the default pair: primary on OPT 1, its backup on OPT 3, as always
    _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                    json={'deviceId': CVT10}))
    card = card_of(client, cid)
    assert [(b['trunkTitle'], b['firstPort'], b['copyRole'],
             b['copyRoleChoice']) for b in card['cvts']] \
        == [('OPT 1', 1, None, False), ('OPT 3', 1, 'backup', True)]
    assert card['nextBoxOnCopy'] is True
    opt3 = card['cvts'][1]['id']
    _ok(client.put(f'/api/processors/{pid}/cvts/{opt3}',
                   json={'copyRole': 'mirror'}))
    card = card_of(client, cid)
    box = card['cvts'][1]
    assert (box['trunkTitle'], box['firstPort'], box['copyRole'],
            box['backupOf']) == ('OPT 3', 21, 'mirror', None)
    assert raw_card(client, cid)['cvts'][1].get('copyOf') \
        == card['cvts'][0]['id']
    assert card['mirrorSockets']['10'] == 30
    assert card['ceiling'] == 20 and card['defined'] == 20
    # ...and back
    _ok(client.put(f'/api/processors/{pid}/cvts/{opt3}',
                   json={'copyRole': 'backup'}))
    box = card_of(client, cid)['cvts'][1]
    assert (box['trunkTitle'], box['firstPort'], box['copyRole']) \
        == ('OPT 3', 1, 'backup')


def test_mx40_pro_add_can_say_mirror_and_40_port_has_no_choice(client):
    pid, cid = mx40(client)
    _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                    json={'deviceId': CVT10, 'copyRole': 'mirror'}))
    boxes = card_of(client, cid)['cvts']
    assert [(b['trunkTitle'], b['copyRole']) for b in boxes] \
        == [('OPT 1', None), ('OPT 3', 'mirror')]
    bad = client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                      json={'deviceId': CVT10, 'copyRole': 'twin'})
    assert bad.status_code == 400
    pid2, cid2 = mx40(client, '40-port')
    add_boxes(client, pid2, cid2, 3)
    box = card_of(client, cid2)['cvts'][2]
    assert (box['firstPort'], box['copyRole'], box['copyRoleChoice']) \
        == (21, None, False)
    refused = client.put(f'/api/processors/{pid2}/cvts/{box["id"]}',
                         json={'copyRole': 'mirror'})
    assert refused.status_code == 400
    assert 'not on a copy OPT' in refused.get_json()['error']


# ── 5. mirror screens ─────────────────────────────────────────────────────

def mirror_rig(client, mode='copy', boxes=4):
    pid = h9(client)
    cid = slot_card(client, pid, 0, H4, mode)
    add_boxes(client, pid, cid, boxes)
    a = screen(client, 'SL')
    b = screen(client, 'SR')
    screens = [{'layerId': str(a), 'name': 'SL', 'ports': 3},
               {'layerId': str(b), 'name': 'SR', 'ports': 3}]
    for i in range(3):
        _ok(pin(client, screens, a, i, cid, i + 1))
    return pid, cid, a, b, screens


def set_mirror(client, b, a, status=200):
    resp = client.put(f'/api/layer/{b}', json={'dataMirrorOf': a})
    assert resp.status_code == status, resp.get_data(as_text=True)
    return resp.get_json()


def test_a_mirror_lands_on_the_copies_of_its_sources_sockets(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    res = resolve(client, screens)
    sr = scr_of(res, b)
    assert sr['mirrorOf'] == str(a)
    assert [(p['cardId'], p['port'], p['source']) for p in sr['ports']] \
        == [(cid, 17, 'mirror'), (cid, 18, 'mirror'), (cid, 19, 'mirror')]
    assert sr['unplaced'] == []
    # the copy box's sockets read as its own silkscreen, 1..3
    assert [p['label'] for p in sr['ports']] == ['1', '2', '3']
    occ = res['occupancy'][cid]
    assert [o['name'] for o in occ['17']] == ['SR']
    assert [o['name'] for o in occ['1']] == ['SL']
    # counts: three primaries and three mirror runs, never one socket twice
    card = summary(res, cid)
    assert card['taken'] == 6 and card['used'] == 3
    assert card['capacity'] == 32 and card['free'] == 13
    copy_box = card_of(client, cid)['cvts'][2]['id']
    assert card['boxes'][copy_box] == {'taken': 3, 'sockets': 8}
    assert not [i for i in res['issues'] if i['layerId'] == str(b)
                if 'layerId' in i]


def test_the_mirror_follows_the_source_when_it_moves(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    _ok(pin(client, screens, a, 0, cid, 12))
    sr = scr_of(resolve(client, screens), b)
    assert sr['ports'][0]['port'] == 28


def test_a_mirror_screen_cannot_be_placed_on_its_own(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    for route, body in (
            ('place', {'index': 0, 'cardId': cid, 'port': 5}),
            ('pin', {'index': 0, 'cardId': cid}),
            ('move-block', {'cardId': cid}),
            ('place-overflow', {'cardId': cid})):
        resp = client.post(f'/api/port-assignments/{route}',
                           json=dict(body, screens=screens, layerId=str(b)))
        assert resp.status_code == 409, (route, resp.get_data(as_text=True))
        # the way back is the new one: unplug the card from the copy
        assert resp.get_json()['error'] == (
            "SR mirrors SL - its ports follow SL's and cannot be placed on "
            "their own. Place SL's ports, or unplug the card from SR to stop "
            "mirroring.")


def _layer(client, layer_id):
    return next(l for l in client.get('/api/project').get_json()['layers']
                if l['id'] == layer_id)


def _source_pins(client, layer_id):
    return [p for p in client.get('/api/project').get_json()
            ['port_assignments']['pins'] if p['layerId'] == str(layer_id)]


def test_unplugging_only_the_copy_just_removes_the_copy(client):
    """Owner, 2026-11-01: "Unplugging only the copy screen just removes the
    copy." A release of the mirror's port (its run's Clear port, its socket
    chip dragged to the tray) stops the mirror; the source keeps its ports."""
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    sent = [dict(s, mirrorOf=str(a)) if s['layerId'] == str(b) else s
            for s in screens]
    body = _ok(client.post('/api/port-assignments/unpin', json={
        'screens': sent, 'layerId': str(b), 'index': 0}))
    assert body['mirrorsCleared'] == [b]
    assert 'dataMirrorOf' not in _layer(client, b)
    sr = scr_of(body['resolution'], b)
    assert sr['mirrorOf'] is None and sr['unplaced'] == [0, 1, 2]
    assert len(_source_pins(client, a)) == 3


def test_unplugging_the_source_unplugs_the_copy(client):
    """Owner, 2026-11-01: "If the card is unplugged from the FIRST (source)
    screen, the copy screen unplugs too." Releasing part of the source
    keeps the copy; releasing its last port on the copy-mode card ends it."""
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    body = _ok(client.post('/api/port-assignments/unpin', json={
        'screens': screens, 'layerId': str(a), 'index': 0}))
    assert 'mirrorsCleared' not in body
    assert _layer(client, b)['dataMirrorOf'] == a
    assert [p['port'] for p in scr_of(body['resolution'], b)['ports']] \
        == [None, 18, 19]
    body = _ok(client.post('/api/port-assignments/unpin', json={
        'screens': screens, 'layerId': str(a)}))
    assert body['mirrorsCleared'] == [b]
    assert 'dataMirrorOf' not in _layer(client, b)
    assert scr_of(body['resolution'], b)['mirrorOf'] is None


def test_a_locked_copy_stays_when_its_source_is_unplugged(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    _ok(client.put(f'/api/layer/{b}', json={'locked': True}), 200)
    body = _ok(client.post('/api/port-assignments/unpin', json={
        'screens': screens, 'layerId': str(a)}))
    assert 'mirrorsCleared' not in body
    assert _layer(client, b)['dataMirrorOf'] == a


def test_moving_the_source_between_copy_cards_keeps_the_copy(client):
    pid, cid, a, b, screens = mirror_rig(client)
    other = slot_card(client, pid, 1, H4, 'copy')
    add_boxes(client, pid, other, 4)
    set_mirror(client, b, a)
    for i in range(3):
        body = _ok(pin(client, screens, a, i, other, i + 1))
    assert 'mirrorsCleared' not in body
    assert _layer(client, b)['dataMirrorOf'] == a
    sr = scr_of(resolve(client, screens), b)
    assert [(p['cardId'], p['port']) for p in sr['ports']] \
        == [(other, 17), (other, 18), (other, 19)]


def test_an_old_saved_show_with_a_mirror_opens_mirrored(client):
    """A show saved by 1.5.4 beta.2/3 (the Screen Info pick) carries
    dataMirrorOf on the layer: it loads, and the copy still lands."""
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    saved = client.get('/api/project').get_json()
    _ok(client.post('/api/project/new', json={}), (200, 201))
    _ok(client.put('/api/project', json=saved), 200)
    assert _layer(client, b)['dataMirrorOf'] == a
    sr = scr_of(resolve(client, screens), b)
    assert sr['mirrorOf'] == str(a)
    assert [p['port'] for p in sr['ports']] == [17, 18, 19]


def test_setting_a_mirror_lets_go_of_its_own_pins(client):
    pid, cid, a, b, screens = mirror_rig(client)
    _ok(pin(client, screens, b, 0, cid, 9))
    set_mirror(client, b, a)
    pins = client.get('/api/project').get_json()['port_assignments']['pins']
    assert all(p['layerId'] != str(b) for p in pins)
    set_mirror(client, b, None)
    assert 'dataMirrorOf' not in next(
        l for l in client.get('/api/project').get_json()['layers']
        if l['id'] == b)


def test_no_socket_takes_a_hand_placed_run_on_a_mirror_box(client):
    pid, cid, a, b, screens = mirror_rig(client)
    other = screen(client, 'C')
    screens.append({'layerId': str(other), 'name': 'C', 'ports': 1})
    resp = pin(client, screens, other, 0, cid, 17)
    assert resp.status_code == 409
    assert 'copies' in resp.get_json()['error'] \
        and 'mirror screen' in resp.get_json()['error']
    box = card_of(client, cid)['cvts'][2]
    resp = client.post('/api/port-assignments/move-block', json={
        'screens': screens, 'layerId': str(other), 'cardId': cid,
        'firstPort': box['firstPort'],
        'lastPort': box['firstPort'] + box['portCount'] - 1})
    assert resp.status_code == 409
    assert 'mirror screen' in resp.get_json()['error']


@pytest.mark.parametrize('mode,boxes,needle', [
    ('copy', 2, 'OPT 3 on '),
    ('independent', 4, 'is in Independent mode - set it to Copy mode'),
    ('backup', 4, 'is in Backup mode - set it to Copy mode'),
])
def test_a_mirror_with_nowhere_to_land_says_what_is_missing(client, mode,
                                                           boxes, needle):
    pid, cid, a, b, screens = mirror_rig(client, mode, boxes)
    set_mirror(client, b, a)
    res = resolve(client, screens)
    sr = scr_of(res, b)
    assert sr['unplaced'] == [0, 1, 2]
    unfed = [i for i in res['issues'] if i['kind'] == 'mirror-unfed']
    assert len(unfed) == 1, res['issues']
    assert unfed[0]['message'].startswith('SR mirrors SL, but ')
    assert needle in unfed[0]['message'], unfed[0]['message']
    assert unfed[0]['message'].endswith(
        'SR ports 1-3 have nowhere to plug in.')
    if mode == 'copy':
        assert 'has no box (it copies OPT 1)' in unfed[0]['message']
    # the generic "not attached" line stays the source's business
    assert not [i for i in res['issues'] if i['kind'] == 'overflow'
                and i['layerId'] == str(b)]


def test_mx40_pro_backup_box_tells_the_mirror_to_set_it_to_mirror(client):
    pid, cid = mx40(client)
    _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                    json={'deviceId': CVT10}))
    a = screen(client, 'SL')
    b = screen(client, 'SR')
    screens = [{'layerId': str(a), 'name': 'SL', 'ports': 2},
               {'layerId': str(b), 'name': 'SR', 'ports': 2}]
    for i in range(2):
        _ok(pin(client, screens, a, i, cid, i + 1))
    set_mirror(client, b, a)
    res = resolve(client, screens)
    msg = next(i for i in res['issues'] if i['kind'] == 'mirror-unfed')
    assert 'is set to Backup - set it to Mirror' in msg['message']
    opt3 = card_of(client, cid)['cvts'][1]['id']
    _ok(client.put(f'/api/processors/{pid}/cvts/{opt3}',
                   json={'copyRole': 'mirror'}))
    sr = scr_of(resolve(client, screens), b)
    assert [p['port'] for p in sr['ports']] == [21, 22]


@pytest.mark.parametrize('change,needle', [
    ({'columns': 5}, 'SR is 5 x 3 cabinets and SL is 4 x 3'),
    ({'rows': 4}, 'SR is 4 x 4 cabinets and SL is 4 x 3'),
    ({'cabinet_width': 176}, "SR's cabinets are 176 x 128 px and SL's are "
                             "128 x 128 px"),
    ({'halfLastColumn': True}, 'SR and SL have different blank, hidden or '
                               'half cabinets, so their ports would not run '
                               'in the same order'),
])
def test_a_size_pixel_or_port_order_mismatch_is_refused(client, change,
                                                        needle):
    a = screen(client, 'SL')
    b = screen(client, 'SR')
    _ok(client.put(f'/api/layer/{b}', json=change), 200)
    body = set_mirror(client, b, a, 409)
    assert body['error'].startswith(needle), body['error']
    assert body['error'].endswith(
        'a mirror screen must match the screen it copies.')
    assert 'dataMirrorOf' not in _layer(client, b)


def test_a_blank_cabinet_in_another_place_is_refused():
    """Ports in the exact same order: a blank cabinet the source does not
    have in that place walks the mirror's ports differently."""
    def layer(name, blanks):
        return {'id': name, 'name': name, 'columns': 2, 'rows': 2,
                'cabinet_width': 128, 'cabinet_height': 128,
                'panels': [{'row': r, 'col': c, 'blank': (r, c) in blanks}
                           for r in range(2) for c in range(2)]}
    assert assignment.mirror_mismatch(layer('A', {(0, 1)}),
                                      layer('B', {(0, 1)})) is None
    why = assignment.mirror_mismatch(layer('A', {(0, 1)}),
                                     layer('B', {(1, 1)}))
    assert why.startswith('B and A have different blank, hidden or half '
                          'cabinets'), why


def test_differing_panel_mm_with_the_same_pixels_is_accepted(client):
    """Owner, 2026-11-01: "they could be differing panel types but be the
    same pixel density per panel" - the physical size is not checked."""
    pid, cid, a, b, screens = mirror_rig(client)
    _ok(client.put(f'/api/layer/{a}', json={'panel_width_mm': 500,
                                            'panel_height_mm': 500}), 200)
    _ok(client.put(f'/api/layer/{b}', json={'panel_width_mm': 600,
                                            'panel_height_mm': 337.5}), 200)
    set_mirror(client, b, a)
    sr = scr_of(resolve(client, screens), b)
    assert sr['mirrorOf'] == str(a)
    assert [p['port'] for p in sr['ports']] == [17, 18, 19]


def test_mirror_chains_self_and_a_second_mirror_are_refused(client):
    a = screen(client, 'SL')
    b = screen(client, 'SR')
    c = screen(client, 'C')
    assert set_mirror(client, a, a, 409)['error'] == 'SL cannot mirror itself.'
    set_mirror(client, b, a)
    assert 'mirrors another screen itself' in set_mirror(client, c, b,
                                                         409)['error']
    assert set_mirror(client, c, a, 409)['error'].startswith(
        'SR already mirrors SL')
    assert 'cannot mirror another screen' in set_mirror(client, a, c,
                                                        409)['error']


def test_a_resize_after_the_mirror_is_set_is_flagged_not_followed(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    _ok(client.put(f'/api/layer/{a}', json={'columns': 6}), 200)
    res = resolve(client, screens)
    flag = [i for i in res['issues'] if i['kind'] == 'mirror-mismatch']
    assert len(flag) == 1
    assert flag[0]['message'].startswith('SR is 4 x 3 cabinets and SL is '
                                         '6 x 3')
    assert scr_of(res, b)['unplaced'] == [0, 1, 2]


def test_a_one_to_one_partner_in_copy_mode_backs_up_the_mirror(client):
    """Owner: "in copy mode you could have a second card doing backup of
    each copy" - the partner's copy sockets carry the mirror's returns."""
    pid, cid, a, b, screens = mirror_rig(client)
    partner = slot_card(client, pid, 1, H4, 'copy')
    add_boxes(client, pid, partner, 4)
    _ok(client.put(f'/api/processors/{pid}', json={'redundancy': True}))
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}',
                   json={'redundancyMode': '1to1', 'backupCardId': partner}))
    set_mirror(client, b, a)
    main = card_of(client, cid)
    by_n = {p['number']: p for p in main['ports']}
    assert by_n[17]['backedBy']['cardId'] == partner
    assert by_n[17]['backedBy']['port'] == 17
    res = resolve(client, screens)
    back = res['occupancy'][partner]['17']
    assert [(o['name'], o['role']) for o in back] == [('SR', 'return')]
    assert summary(res, partner)['taken'] == 6


# ── 6. per port: card ethernet or breakout box ────────────────────────────

def test_mx40_pro_port_plugs_in_at_the_unit_or_the_box(client):
    pid, cid = mx40(client, '40-port')
    add_boxes(client, pid, cid, 2)
    card = card_of(client, cid)
    # today's drawing: a port a box carries plugs in at the box
    p3 = next(p for p in card['ports'] if p['number'] == 3)
    assert (p3['plug'], p3['cvtId']) == ('box', card['cvts'][0]['id'])
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}/ports/3',
                   json={'plug': 'card'}))
    card = card_of(client, cid)
    p3 = next(p for p in card['ports'] if p['number'] == 3)
    assert (p3['plug'], p3['cvtId']) == ('card', None)
    assert 3 not in [p['number'] for p in card['cvts'][0]['ports']]
    assert raw_card(client, cid)['ethernetPorts'] == [3]
    assert card['delivered'] == 20
    # the "all ports on this OPT" shortcut
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}',
                   json={'ethernetPorts': list(range(11, 21))}))
    card = card_of(client, cid)
    assert card['cvts'][1]['ports'] == []
    assert [p['plug'] for p in card['ports'] if p['number'] > 10] \
        == ['card'] * 10
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}',
                   json={'ethernetPorts': []}))
    assert 'ethernetPorts' not in raw_card(client, cid)


def test_the_plug_choice_is_refused_where_there_is_none(client):
    pid, cid = mx40(client, '40-port')
    add_boxes(client, pid, cid, 3)
    # 21-40 are OPT 3/4's alone: no RJ45 carries them
    resp = client.put(f'/api/processors/{pid}/cards/{cid}/ports/25',
                      json={'plug': 'card'})
    assert resp.status_code == 400
    # a port no box carries plugs in at the unit only
    resp = client.put(f'/api/processors/{pid}/cards/{cid}/ports/15',
                      json={'plug': 'box'})
    assert resp.status_code == 200
    pid2, cid2 = mx40(client, '40-port')
    resp = client.put(f'/api/processors/{pid2}/cards/{cid2}/ports/2',
                      json={'plug': 'card'})
    assert resp.status_code == 400
    assert 'no breakout box carrying it' in resp.get_json()['error']
    hid = h9(client)
    h20 = slot_card(client, hid, 0, H20)
    resp = client.put(f'/api/processors/{hid}/cards/{h20}/ports/1',
                      json={'plug': 'card'})
    assert resp.status_code == 400
    # an unnamed chassis card reads Card N, never slot N or its model
    assert resp.get_json()['error'].startswith(
        'Card 1 has no ports that plug in at both')


def test_h16_port_plugs_in_at_the_card_or_the_box(client):
    hid = h9(client)
    cid = slot_card(client, hid, 0, H16)
    add_boxes(client, hid, cid, 1)
    _ok(client.put(f'/api/processors/{hid}/cards/{cid}/ports/2',
                   json={'plug': 'card'}))
    card = card_of(client, cid)
    plugs = {p['number']: p['plug'] for p in card['ports']}
    assert plugs[1] == 'box' and plugs[2] == 'card' and plugs[9] is None
    assert len(card['cvts'][0]['ports']) == 7


# ── 7. cards that cannot load one screen together ─────────────────────────

def test_fiber_and_rj45_h_cards_never_load_one_screen(client):
    hid = h9(client)
    fiber = slot_card(client, hid, 0, H4)
    add_boxes(client, hid, fiber, 1)
    rj = slot_card(client, hid, 1, H20)
    a = screen(client, 'W')
    screens = [{'layerId': str(a), 'name': 'W', 'ports': 2}]
    _ok(pin(client, screens, a, 0, fiber, 1))
    resp = pin(client, screens, a, 1, rj, 1)
    assert resp.status_code == 409
    err = resp.get_json()['error']
    # an unnamed chassis card reads Card N, never slot N
    assert err.startswith('W cannot be loaded by both H_4xfiber (H9 Card 1) '
                          'and H_20xRJ45 (H9 Card 2)'), err
    assert 'NovaStar does not allow those cards to load the same screen' \
        in err


def test_enhanced_cards_in_different_modes_never_load_one_screen(client):
    hid = h9(client)
    one = slot_card(client, hid, 0, H4E, 'copy')
    two = slot_card(client, hid, 1, H4E, 'backup')
    add_boxes(client, hid, one, 1)
    add_boxes(client, hid, two, 1)
    a = screen(client, 'W')
    screens = [{'layerId': str(a), 'name': 'W', 'ports': 2}]
    _ok(pin(client, screens, a, 0, one, 1))
    resp = pin(client, screens, a, 1, two, 1)
    assert resp.status_code == 409
    assert 'in different modes' in resp.get_json()['error']
    # same mode is fine...
    _ok(client.put(f'/api/processors/{hid}/cards/{two}',
                   json={'mode': 'copy'}))
    _ok(pin(client, screens, a, 1, two, 1))
    # ...and a mode change that would split the screen is refused
    resp = client.put(f'/api/processors/{hid}/cards/{two}',
                      json={'mode': 'backup'})
    assert resp.status_code == 409
    assert 'in different modes' in resp.get_json()['error']
    assert raw_card(client, two)['mode'] == 'copy'


def test_mix_reason_is_symmetric_and_reads_the_catalog():
    cards = [{'cardId': 'a', 'deviceId': H16, 'deviceName': 'H_16xRJ45+2xfiber',
              'name': 'A', 'processorName': '', 'slot': 0, 'mode': 'default',
              'modes': []},
             {'cardId': 'b', 'deviceId': H4E, 'deviceName': 'H_4xfiber '
              '(enhanced)', 'name': 'B', 'processorName': '', 'slot': 1,
              'mode': 'backup', 'modes': []}]
    assert assignment._mix_reason('W', cards)
    assert assignment._mix_reason('W', list(reversed(cards)))
    assert assignment._mix_reason('W', [cards[0], copy.deepcopy(cards[0])]) \
        is None
