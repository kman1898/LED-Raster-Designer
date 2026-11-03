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
SHAPES = [
    # 1. a CVT4K-S on OPT 5-6 behind CVT10s on OPT 1 and 2
    ('h4e-cvt4k-behind-cvt10s', H4E, 'backup', 'copy',
     [CVT10] * 4 + [CVT4K],
     {'OPT 5-6': run(range(1, 11), 'OPT 1', 1)
      + run(range(11, 17), 'OPT 2', 1)}, 40),
    # 2. CVT10s on OPT 5 and 6 behind a CVT4K-S on OPT 1-2
    ('h4e-cvt10s-behind-cvt4k', H4E, 'backup', 'copy',
     [CVT4K, CVT4K, CVT10, CVT10],
     {'OPT 5': run(range(1, 11), 'OPT 1-2', 1),
      'OPT 6': run(range(11, 17), 'OPT 1-2', 11, socket_first=1)}, 32),
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
     {'OPT 3-4': run(range(1, 11), 'OPT 1', 1)
      + run(range(11, 17), 'OPT 2', 1)}, 20),
    # ...where ports 17-20, on no box, are the MX40 Pro's own RJ45s, and
    # the OPT 4 box's sockets 7-10 back those up
    ('mx40-cvt10s-behind-cvt4k', MX40, '20-port', '40-port',
     [CVT4K, CVT10, CVT10],
     {'OPT 3': run(range(1, 11), 'OPT 1-2', 1),
      'OPT 4': run(range(11, 17), 'OPT 1-2', 11, socket_first=1)
      + run(range(17, 21), 'own', 17, socket_first=7)}, 20),
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
    OPT 1-2 and 3-4. Ports 17-20 came only out of the OPT 6 backup, and the
    card read 36. The primaries carry 32."""
    pid, cid = rig(client, H4E, 'backup')
    add_boxes(client, pid, cid, [CVT4K, CVT4K, CVT10, CVT10])
    card = card_of(client, cid)
    assert card['ceiling'] == 32, card['ceiling']
    assert card['defined'] == 32, card['defined']
    numbers = [p['number'] for p in card['ports']]
    assert not any(17 <= n <= 20 for n in numbers), numbers
    assert sum(1 for p in card['ports'] if not p['mirrorOf']) == 32


def test_the_mx40_pros_own_ports_past_the_primary_box_stay_its_own(client):
    """MX40 Pro, CVT4K-S on OPT 1-2: ports 17-20 are its own RJ45s, not the
    OPT 4 backup box's - the backup box backs them up, on its sockets
    7-10, and they are no box's ports."""
    pid, cid = rig(client, MX40, '20-port')
    add_boxes(client, pid, cid, [CVT4K, CVT10, CVT10])
    card = card_of(client, cid)
    face = [p['number'] for p in card['ports'] if not p['cvtId']]
    assert face == [17, 18, 19, 20]


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
     range(1, 17), 20),
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
    first = min(backed)
    assert mapping(card) == {opts: [(n, n - first + 1, 'own', n)
                                    for n in backed]}
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


def test_the_rule_is_the_catalogs_copy_word_and_nothing_else(client,
                                                             monkeypatch):
    """A VX1000 Pro's OPT 2 copies its Ethernet ports, but until its
    catalog mode carries a sourced copyTrunks nothing is offered. Given
    one, the same rule backs up its own ports 1-10 from a CVT10 on OPT 2."""
    pid, cid = rig(client, VX1000_PRO)
    card = card_of(client, cid)
    if catalog.copy_trunks(catalog.get_device(VX1000_PRO), card['mode']):
        pytest.skip('the VX1000 Pro has a copyTrunks of its own now')
    assert card['copyTrunksOpen'] == []
    assert add_on_copy(client, pid, cid, CVT10, 1).status_code == 400
    mode = catalog.mode_entry(catalog.get_device(VX1000_PRO), card['mode'])
    monkeypatch.setitem(mode, 'copyTrunks', 'per-box')
    assert card_of(client, cid)['copyTrunksOpen'] == [1]
    _ok(add_on_copy(client, pid, cid, CVT10, 1))
    card = card_of(client, cid)
    assert mapping(card) == {'OPT 2': run(range(1, 11), 'own', 1)}
    assert card['ceiling'] == 10 and len(_own_ports(card)) == 10


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
    for (const b of backups) {
        app._setDataCableSheetOpen({ kind: 'cvt', id: b.id }, true);
    }
    app.renderHardwareDock();
    for (const b of backups) {
        const sheet = document.querySelector(
            `[data-lrd-cable-sheet="cvt:${b.id}"]`);
        sheets[b.trunkTitle] = sheet ? [...sheet.querySelectorAll('tr')]
            .filter(tr => tr.children[0] && tr.children[0].tagName === 'TD'
                    && !tr.classList.contains('hw-dock-cable-snake'))
            .map(tr => parseInt(tr.children[1].textContent, 10)) : null;
        app._setDataCableSheetOpen({ kind: 'cvt', id: b.id }, false);
    }
    app.renderHardwareDock();
    unit = unit || document.querySelector(
        `[data-lrd-loop-own="${cardId}"]`)?.closest('.hw-dock-unit, .hw-dock-card');
    return {
        strips,
        ownRows,
        sheets,
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
    for number, _socket, primary, local in rows:
        groups.setdefault(primary, ([], []))
        groups[primary][0].append(local)
        groups[primary][1].append(number)

    def text(ns):
        return f'{min(ns)}-{max(ns)}'
    parts = []
    for primary, (locals_, numbers) in groups.items():
        mine, shown = text(locals_), text(numbers)
        primary = 'own ports' if primary == 'own' else primary
        parts.append(f'{primary} {mine}'
                     + (f' as {shown}' if shown != mine else ''))
    return 'loop of ' + ', '.join(parts)


@pytest.mark.parametrize(PARAMS, SHAPES, ids=IDS)
def test_the_tray_draws_each_backup_socket_in_its_primarys_loop(
        e2e_server, pw_browser, name, unit, mode, other, boxes, expected,
        count):
    kind = catalog.get_device(unit)['kind']
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
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
        for number, _socket, primary, _local in rows:
            fars = want.setdefault(primary, [])
            if not fars or fars[-1][0] != backup:
                fars.append([backup, []])
            fars[-1][1].append(number)
    assert tray['ownRows'] == want.pop('own', []), tray['ownRows']
    assert set(tray['strips']) == set(want), tray['strips']
    for primary, fars in want.items():
        strip = tray['strips'][primary]
        assert strip and strip['loop'], (primary, strip)
        assert strip['fars'] == fars, (primary, strip['fars'])
    # no backup box drawn on its own, and no "(copy)" box of free sockets
    assert tray['alone'] == [], tray['alone']
    assert not tray['copyTag']
    # the backup's cable sheet: every socket, by the port it backs up
    assert tray['sheets'] == {b: [r[0] for r in rows]
                              for b, rows in expected.items()}
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


def test_the_tray_draws_the_own_ports_backup_as_loop_rows(e2e_server,
                                                          pw_browser):
    """A UHD Jr with no box on OPT 1/2: "+ Box" offers the copy OPTs, and
    a CVT4K-S put on OPT 3-4 draws as the loop end of the unit's own 16
    ports, right under them."""
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
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
        assert {'CVT10 on OPT 3', 'CVT4K-S on OPT 3-4'} <= set(offered), \
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
