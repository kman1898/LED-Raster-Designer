"""An opticalCON DUO or QUAD is shared across boxes, the way a TAC is.

The owner (2026-10-08): "I need to be able to use opticalCON QUAD or DUO
etc across CVTs or XDs. XDs can only be pairs so a DUO can't split XDs but
QUADs could. And on CVTs if say I am using BiDi or 1 OPT port I need to be
able to put them on different boxes."

So an opticalCON is no longer one box's (the 1.4.0 `ownerBoxId`): any
box's link - a backup input's included - picks it and takes its next free
strands, a strand carries one link, and the cable goes when its last link
lets go. Nothing special-cases a model - the strand counts do it: an XD
link needs 2, so a DUO fills one XD input and a QUAD feeds two; a BiDi
link needs 1, so a DUO feeds two and a QUAD four; a CVT4K-S on one OPT
needs 2, so a QUAD feeds two of them. A 1.4.0 file keeps every link it
had. The box's Fiber select offers every opticalCON with the strands the
link needs; the binder prints each link's strands on one (crossing inside
at the breakout, as an MTP's do); the pull sheet counts it once.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_shared_opticalcon.py -v --browser chromium
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402
from conftest import settled  # noqa: E402

H4 = 'novastar-card-h-4xfiber'
CVT4K = 'novastar-cvt4k-s'


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


def _state(client):
    return client.get('/api/processors').get_json()


def _h5(client):
    """An H5 with an H_4xfiber in slots 0 and 1, each with two CVT4K-S on
    BiDi - the shape of the owner's show: [(pid, cardId, [boxA, boxB])]."""
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h5'}), 201)
    pid = st['processors'][-1]['id']
    out = []
    for i in (0, 1):
        st = _ok(client.put(f'/api/processors/{pid}/slots/{i}', json={'deviceId': H4}))
        proc = next(p for p in st['processors'] if p['id'] == pid)
        cid = next(s for s in proc['slots'] if s['index'] == i)['card']['id']
        boxes = []
        for _ in range(2):
            st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                                 json={'deviceId': CVT4K, 'pair': False}), 201)
            card = next(s for s in next(p for p in st['processors'] if p['id'] == pid)['slots']
                        if s['index'] == i)['card']
            boxes = [b['id'] for b in card['cvts']]
        for box in boxes:
            _ok(client.put(f'/api/processors/{pid}/cvts/{box}/fiber', json={'bidi': True}))
        out.append((pid, cid, boxes))
    return out


def _sx40(client, backup=None):
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sx40'}), 201)
    sx = st['processors'][-1]
    if backup:
        _ok(client.put(f"/api/processors/{sx['id']}", json={'backupUnit': {'name': backup}}))
    return sx['id'], [b['id'] for b in sx['slots'][0]['card']['cvts']]


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


def _links(client, box_id):
    return (_raw_box(client, box_id) or {}).get('fiberLinks')


def _link(client, pid, box, key, body):
    return client.put(f'/api/processors/{pid}/cvts/{box}/fiber-links/{key}', json=body)


def _new(client, kind, box, key, **kw):
    st = _ok(client.post('/api/fiber-cables', json=dict(kind=kind, link={'boxId': box, 'key': key},
                                                         **kw)), 201)
    return st['fiberCables'][-1]


# ── the store, through the Flask client ──────────────────────────────────

def test_a_quad_feeds_four_bidi_links_on_two_cvt4k_boxes_on_two_cards(client):
    """The owner's show: QUAD 1 made on P (A)'s OPT 1 takes strand 1, its
    OPT 2 strand 2; P (B) - on the OTHER card - picks QUAD 1 and its OPT 1
    and OPT 2 take 3 and 4. A fifth BiDi link finds no free strand."""
    (pid, _c1, (pa, _pb)), (_pid, _c2, (ra, rb)) = _h5(client)
    quad = _new(client, 'opticalcon-quad', pa, 'p1', ft=500)
    assert (quad['name'], quad['strands'], quad['ft']) == ('QUAD 1', 4, 500)
    assert 'ownerBoxId' not in quad
    _ok(_link(client, pid, pa, 'p2', {'cable': quad['id']}))
    assert _links(client, pa) == {'p1': {'cable': quad['id'], 'strands': [1]},
                                  'p2': {'cable': quad['id'], 'strands': [2]}}
    _ok(_link(client, pid, ra, 'p1', {'cable': quad['id']}))
    _ok(_link(client, pid, ra, 'p2', {'cable': quad['id']}))
    assert _links(client, ra) == {'p1': {'cable': quad['id'], 'strands': [3]},
                                  'p2': {'cable': quad['id'], 'strands': [4]}}
    why = _refused(_link(client, pid, rb, 'p1', {'cable': quad['id']}))
    assert why == 'QUAD 1 has no 1 free strand left.', why
    # a strand another box holds is refused by name
    why = _refused(_link(client, pid, rb, 'p1', {'cable': quad['id'], 'strands': [3]}))
    assert 'strand 3 Green is already used by' in why and 'a strand carries one link' in why, why
    assert _links(client, rb) is None


def test_a_duo_feeds_two_bidi_links_on_different_boxes(client):
    (pid, _c1, (pa, pb)), _second = _h5(client)
    duo = _new(client, 'opticalcon-duo', pa, 'p1')
    _ok(_link(client, pid, pb, 'p1', {'cable': duo['id']}))
    assert _links(client, pa)['p1'] == {'cable': duo['id'], 'strands': [1]}
    assert _links(client, pb)['p1'] == {'cable': duo['id'], 'strands': [2]}
    assert 'no 1 free strand' in _refused(_link(client, pid, pb, 'p2', {'cable': duo['id']}))


def test_a_quad_feeds_two_cvt4k_boxes_on_one_opt_each(client):
    """A CVT4K-S switched to one OPT (not BiDi) needs 2 strands a link: a
    QUAD feeds two such boxes, 1-2 and 3-4."""
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': H4}))
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    for _ in range(2):
        st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                             json={'deviceId': CVT4K, 'pair': False, 'inputs': 1}), 201)
    a, b = [x['id'] for x in next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['cvts']]
    assert _res_box(client, a)['fiberLinkKeys'] == ['p1']
    quad = _new(client, 'opticalcon-quad', a, 'p1')
    _ok(_link(client, pid, b, 'p1', {'cable': quad['id']}))
    assert _links(client, a) == {'p1': {'cable': quad['id'], 'strands': [1, 2]}}
    assert _links(client, b) == {'p1': {'cable': quad['id'], 'strands': [3, 4]}}


def test_a_duo_fills_one_xd_input_and_no_second_xd_takes_it(client):
    """An XD link needs 2 strands - the DUO's both - so no other XD can
    take it. No special case: the strand count says so."""
    sx, xds = _sx40(client)
    duo = _new(client, 'opticalcon-duo', xds[0], 'p1')
    assert _links(client, xds[0]) == {'p1': {'cable': duo['id'], 'strands': [1, 2]}}
    why = _refused(_link(client, sx, xds[1], 'p1', {'cable': duo['id']}))
    assert why == f"{duo['name']} has no 2 free strands left.", why
    why = _refused(_link(client, sx, xds[1], 'p1', {'cable': duo['id'], 'strands': [2]}))
    assert 'needs 2 strands' in why, why
    assert _links(client, xds[1]) is None


def test_a_quad_feeds_two_xd_inputs_on_different_xds(client):
    sx, xds = _sx40(client)
    quad = _new(client, 'opticalcon-quad', xds[0], 'p1')
    _ok(_link(client, sx, xds[1], 'p1', {'cable': quad['id']}))
    assert _links(client, xds[0]) == {'p1': {'cable': quad['id'], 'strands': [1, 2]}}
    assert _links(client, xds[1]) == {'p1': {'cable': quad['id'], 'strands': [3, 4]}}
    assert 'no 2 free strands' in _refused(_link(client, sx, xds[2], 'p1', {'cable': quad['id']}))


def test_backup_inputs_take_a_shared_opticalcon(client):
    """With a backup processor an XD's X2 picks the QUAD its X1 rides - by
    name, or by the backup link's default (the primary's cable) - and takes
    the next free strands; a CVT4K-S's OPT 3 the same."""
    sx, xds = _sx40(client, backup='SX BU')
    assert 'b1' in _res_box(client, xds[0])['fiberLinkKeys']
    quad = _new(client, 'opticalcon-quad', xds[0], 'p1')
    _ok(_link(client, sx, xds[0], 'b1', {}))                          # the primary's cable
    assert _links(client, xds[0]) == {'p1': {'cable': quad['id'], 'strands': [1, 2]},
                                      'b1': {'cable': quad['id'], 'strands': [3, 4]}}
    duo = _new(client, 'opticalcon-duo', xds[1], 'p1')
    why = _refused(_link(client, sx, xds[2], 'b1', {'cable': duo['id']}))
    assert 'no 2 free strands' in why, why
    # a CVT4K-S on BiDi behind an H9 with a backup unit: OPT 3 and OPT 4
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': H4}))
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': CVT4K, 'pair': False}), 201)
    box = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['cvts'][0]['id']
    _ok(client.put(f'/api/processors/{pid}/cvts/{box}/fiber', json={'bidi': True}))
    _ok(client.put(f'/api/processors/{pid}', json={'backupUnit': {'name': 'H9 BU'}}))
    assert _res_box(client, box)['fiberLinkKeys'] == ['p1', 'p2', 'b1', 'b2']
    q2 = _new(client, 'opticalcon-quad', box, 'p1')
    for key in ('p2', 'b1', 'b2'):
        _ok(_link(client, pid, box, key, {'cable': q2['id']}))
    assert {k: v['strands'] for k, v in _links(client, box).items()} == \
        {'p1': [1], 'p2': [2], 'b1': [3], 'b2': [4]}


def test_the_box_it_was_made_on_going_keeps_it_while_another_link_uses_it(client):
    """An opticalCON follows the shared-cable lifecycle: deleting the box it
    was made on drops that box's links only; the cable stays while any
    link names it and goes with the last."""
    (pid, _c1, (pa, pb)), _second = _h5(client)
    quad = _new(client, 'opticalcon-quad', pa, 'p1')
    _ok(_link(client, pid, pb, 'p1', {'cable': quad['id']}))
    st = _ok(client.delete(f'/api/processors/{pid}/cvts/{pa}'))
    assert quad['id'] in [c['id'] for c in st['fiberCables']]
    assert _links(client, pb) == {'p1': {'cable': quad['id'], 'strands': [2]}}
    # the freed strand is free again
    _ok(_link(client, pid, pb, 'p2', {'cable': quad['id']}))
    assert _links(client, pb)['p2']['strands'] == [1]
    st = _ok(client.delete(f'/api/processors/{pid}/cvts/{pb}'))
    assert quad['id'] not in [c['id'] for c in st['fiberCables'] or []]


def test_a_1_4_0_file_with_owner_box_ids_loads_with_every_link(client):
    """A file saved by 1.4.0 names each opticalCON's box (ownerBoxId). It
    loads with every link it had; the field is dropped; and another box can
    now pick the cable - P (B) gets QUAD 1's strands 3 and 4."""
    (pid, _c1, (pa, pb)), (_pid, _c2, (ra, rb)) = _h5(client)
    project = client.get('/api/project').get_json()
    project['fiberCables'] = [
        {'id': 'fib901', 'kind': 'opticalcon-quad', 'name': 'QUAD 1', 'strands': 4, 'ft': 500,
         'labels': 'numbers', 'subunits': False, 'strandNames': {}, 'ownerBoxId': pa},
        {'id': 'fib902', 'kind': 'opticalcon-quad', 'name': 'QUAD 2', 'strands': 4, 'ft': 1000,
         'labels': 'colors', 'subunits': False, 'strandNames': {}, 'ownerBoxId': ra},
        {'id': 'fib903', 'kind': 'opticalcon-duo', 'name': 'DUO 1', 'strands': 2,
         'labels': 'colors', 'subunits': False, 'strandNames': {}, 'ownerBoxId': rb},
    ]
    for proc in project['processors']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == pa:
                    box['fiberLinks'] = {'p1': {'cable': 'fib901', 'strands': [1]},
                                         'p2': {'cable': 'fib901', 'strands': [2]}}
                if box['id'] == ra:
                    box['fiberLinks'] = {'p1': {'cable': 'fib902', 'strands': [1]},
                                         'p2': {'cable': 'fib902', 'strands': [2]}}
    project['next_processor_seq'] = max(project.get('next_processor_seq') or 0, 904)
    _ok(client.put('/api/project', json=project))
    loaded = client.get('/api/project').get_json()
    assert [c['id'] for c in loaded['fiberCables']] == ['fib901', 'fib902', 'fib903']
    assert not [c for c in loaded['fiberCables'] if 'ownerBoxId' in c], loaded['fiberCables']
    assert _links(client, pa) == {'p1': {'cable': 'fib901', 'strands': [1]},
                                  'p2': {'cable': 'fib901', 'strands': [2]}}
    assert _links(client, ra) == {'p1': {'cable': 'fib902', 'strands': [1]},
                                  'p2': {'cable': 'fib902', 'strands': [2]}}
    assert not [c for c in _state(client)['fiberCables'] if 'ownerBoxId' in c]
    _ok(_link(client, pid, pb, 'p1', {'cable': 'fib901'}))
    _ok(_link(client, pid, pb, 'p2', {'cable': 'fib901'}))
    assert _links(client, pb) == {'p1': {'cable': 'fib901', 'strands': [3]},
                                  'p2': {'cable': 'fib901', 'strands': [4]}}
    # the R boxes pick where strands are free; the DUO made on R (B) in
    # 1.4.0 (no link yet) is any box's now
    _ok(_link(client, pid, rb, 'p1', {'cable': 'fib902'}))
    assert _links(client, rb)['p1'] == {'cable': 'fib902', 'strands': [3]}
    assert 'no 1 free strand' in _refused(_link(client, pid, rb, 'p2', {'cable': 'fib901'}))
    _ok(_link(client, pid, pa, 'p2', {'cable': 'fib903'}))
    assert _links(client, pa)['p2'] == {'cable': 'fib903', 'strands': [1]}


def test_settle_drops_owner_box_id_once_and_keeps_the_links():
    box = {'id': 'cvt5', 'deviceId': CVT4K, 'bidi': True,
           'fiberLinks': {'p1': {'cable': 'fib9', 'strands': [1]}}}
    other = {'id': 'cvt6', 'deviceId': CVT4K, 'bidi': True,
             'fiberLinks': {'p1': {'cable': 'fib9', 'strands': [2]}}}
    project = {'processors': [{'id': 'proc1', 'deviceId': 'novastar-h9', 'slots': [
        {'index': 0, 'card': {'id': 'card2', 'deviceId': H4, 'mode': 'independent',
                              'cvts': [box, other]}}]}],
        'fiberCables': [{'id': 'fib9', 'kind': 'opticalcon-quad', 'strands': 4,
                         'name': 'QUAD 1', 'ownerBoxId': 'cvt5'}]}
    before = copy.deepcopy(project)
    assert catalog.settle_fiber(project) is True
    assert 'ownerBoxId' not in project['fiberCables'][0]
    assert box['fiberLinks'] == before['processors'][0]['slots'][0]['card']['cvts'][0]['fiberLinks']
    # the link on the box that did NOT own it in 1.4.0 terms stays too
    assert other['fiberLinks'] == {'p1': {'cable': 'fib9', 'strands': [2]}}
    assert catalog.settle_fiber(project) is False


def test_an_opticalcon_needs_no_box_to_be_made(client):
    """Like a TAC, an opticalCON can be made with no link yet; a strand
    count other than the connector's is still refused."""
    st = _ok(client.post('/api/fiber-cables', json={'kind': 'opticalcon-duo'}), 201)
    assert st['fiberCables'][-1]['strands'] == 2
    assert 'has 4 fibers' in _refused(client.post('/api/fiber-cables',
                                                  json={'kind': 'opticalcon-quad', 'strands': 2}))


# ── the browser: the Fiber select, the binder, the pull sheet ───────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# WAMU-shaped: an H5 with two H_4xfiber cards, SC1 and SC2, each with two
# CVT4K-S on BiDi - P (A), P (B) on SC1, R (A), R (B) on SC2. QUAD 1 (500')
# takes P (A)'s OPT 1 and OPT 2 on strands 1 and 2; QUAD 2 (1000') R (A)'s
# the same. An SX40: QUAD 3 on XD A's X1 (1-2) and XD B's X1 (3-4). One
# screen, so the pull sheet has a position.
def test_a_quad_on_bidi_feeds_four_cvts_one_strand_each(client):
    """The owner: on BiDi a QUAD can in theory reach four CVTs. Four CVT4K-S
    on one OPT each (`inputs: 1`, one link apiece) fill an H_4xfiber's four
    trunks; on BiDi each link takes one strand, so one QUAD feeds all four -
    strand 1, 2, 3, 4 - and a fifth box's link finds none left."""
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': H4}))
    cid = next(s for s in next(p for p in st['processors'] if p['id'] == pid)['slots']
               if s['index'] == 0)['card']['id']
    for _ in range(4):
        st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                             json={'deviceId': CVT4K, 'inputs': 1, 'pair': False}), 201)
    card = next(s for s in next(p for p in st['processors'] if p['id'] == pid)['slots']
                if s['index'] == 0)['card']
    boxes = [b['id'] for b in card['cvts']]
    assert len(boxes) == 4
    for box in boxes:
        assert _raw_box(client, box)['inputs'] == 1
        _ok(client.put(f'/api/processors/{pid}/cvts/{box}/fiber', json={'bidi': True}))
        assert _res_box(client, box)['fiberLinkKeys'] == ['p1'], _res_box(client, box)['fiberLinkKeys']
    quad = _new(client, 'opticalcon-quad', boxes[0], 'p1')
    for box in boxes[1:]:
        _ok(_link(client, pid, box, 'p1', {'cable': quad['id']}))
    assert [_links(client, b)['p1'] for b in boxes] == [
        {'cable': quad['id'], 'strands': [n]} for n in (1, 2, 3, 4)]
    # a fifth CVT, on the next card, finds no strand left on the QUAD
    st = _ok(client.put(f'/api/processors/{pid}/slots/1', json={'deviceId': H4}))
    cid2 = next(s for s in next(p for p in st['processors'] if p['id'] == pid)['slots']
                if s['index'] == 1)['card']['id']
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid2}/cvts',
                         json={'deviceId': CVT4K, 'inputs': 1, 'pair': False}), 201)
    fifth = next(s for s in next(p for p in st['processors'] if p['id'] == pid)['slots']
                 if s['index'] == 1)['card']['cvts'][0]['id']
    _ok(client.put(f'/api/processors/{pid}/cvts/{fifth}/fiber', json={'bidi': True}))
    assert 'free strand' in _refused(_link(client, pid, fifth, 'p1', {'cable': quad['id']}))


def test_a_quad_on_bidi_reaches_four_two_opt_cvts_by_their_first_link(client):
    """The owner's own shape - two H_4xfiber cards, two CVT4K-S on BiDi on
    each - with every box using only its OPT 1: one QUAD reaches all four
    boxes across both cards, a strand each."""
    (pid, _c1, (a, b)), (_pid, _c2, (c, d)) = _h5(client)
    quad = _new(client, 'opticalcon-quad', a, 'p1')
    for box in (b, c, d):
        _ok(_link(client, pid, box, 'p1', {'cable': quad['id']}))
    assert [_links(client, x)['p1']['strands'] for x in (a, b, c, d)] == [[1], [2], [3], [4]]
    assert 'free strand' in _refused(_link(client, pid, a, 'p2', {'cable': quad['id']}))


SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'W1', columns: 4, rows: 4,
                                       cabinet_width: 200, cabinet_height: 200,
                                       processorType: 'novastar-armor'});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h5', name: 'WAMU'});
    const pid = st.processors[st.processors.length - 1].id;
    const boxes = [];
    for (const i of [0, 1]) {
        st = await j('PUT', `/api/processors/${pid}/slots/${i}`, {deviceId: 'novastar-card-h-4xfiber'});
        const cid = st.processors.find(p => p.id === pid).slots.find(s => s.index === i).card.id;
        await j('PUT', `/api/processors/${pid}/cards/${cid}`, {name: i ? 'SC2' : 'SC1'});
        for (let k = 0; k < 2; k++) {
            st = await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`,
                         {deviceId: 'novastar-cvt4k-s', pair: false});
        }
        const ids = st.processors.find(p => p.id === pid).slots.find(s => s.index === i).card.cvts.map(b => b.id);
        const names = i ? ['R (A)', 'R (B)'] : ['P (A)', 'P (B)'];
        for (let k = 0; k < 2; k++) {
            await j('PUT', `/api/processors/${pid}/cvts/${ids[k]}`, {name: names[k]});
            await j('PUT', `/api/processors/${pid}/cvts/${ids[k]}/fiber`, {bidi: true});
        }
        boxes.push(...ids);
    }
    const [pa, pb, ra, rb] = boxes;
    const last = (s) => s.fiberCables[s.fiberCables.length - 1];
    st = await j('POST', '/api/fiber-cables', {kind: 'opticalcon-quad', ft: 500, link: {boxId: pa, key: 'p1'}});
    const q1 = last(st);
    await j('PUT', `/api/processors/${pid}/cvts/${pa}/fiber-links/p2`, {cable: q1.id});
    st = await j('POST', '/api/fiber-cables', {kind: 'opticalcon-quad', ft: 1000, link: {boxId: ra, key: 'p1'}});
    const q2 = last(st);
    await j('PUT', `/api/processors/${pid}/cvts/${ra}/fiber-links/p2`, {cable: q2.id});
    st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40'});
    const sx = st.processors[st.processors.length - 1];
    const xds = sx.slots[0].card.cvts.map(b => b.id);
    st = await j('POST', '/api/fiber-cables', {kind: 'opticalcon-quad', ft: 300, link: {boxId: xds[0], key: 'p1'}});
    const q3 = last(st);
    await j('PUT', `/api/processors/${sx.id}/cvts/${xds[1]}/fiber-links/p1`, {cable: q3.id});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('shared_opticalcon_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Shared opticalCON Seed');
    return {pid, pa, pb, ra, rb, sx: sx.id, xds, q1: q1.id, q2: q2.id, q3: q3.id};
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

ROWS_JS = """(boxId) => {
    const sec = document.querySelector(`[data-lrd-fiber-row="${boxId}"]`);
    if (!sec) return null;
    return [...sec.querySelectorAll('.hw-dock-fiber-link')].map(r => ({
        role: r.querySelector('.hw-dock-fiber-role').textContent,
        value: r.querySelector('select').value,
        options: [...r.querySelector('select').options].map(o => o.textContent),
        chips: [...r.querySelectorAll('.hw-dock-fiber-strand')].map(c => c.textContent),
    }));
}"""

PUT_JS = """async ([url, body]) => {
    const r = await fetch(url, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const out = await r.json();
    await window.app.refreshProcessors(); await window.app.refreshPortAssignment();
    return out;
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
    settled(pg, lambda: pg.evaluate(
        "(sx) => !!(window.app._processorsResolved || []).find(p => p.id === sx)", ids['sx']),
        bool, 5000)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _served(pg):
    return pg.evaluate("async () => (await (await fetch('/api/processors')).json())")


def _box_links(st, box_id):
    for proc in st['processors']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == box_id:
                    return box.get('fiberLinks')
    return None


def _rows(pg, box_id):
    assert pg.evaluate(OPEN_SHEET_JS, box_id), f'the cable sheet of {box_id} did not open'
    return settled(pg, lambda: pg.evaluate(ROWS_JS, box_id), bool)


def _shared(pg, ids):
    """P (B) on QUAD 1's strands 3 and 4, R (B)'s OPT 1 on QUAD 2's 3 -
    what the select test picks - set directly, so each test stands alone."""
    pid = ids['pid']
    for box, key, cable, strands in ((ids['pb'], 'p1', ids['q1'], [3]), (ids['pb'], 'p2', ids['q1'], [4]),
                                     (ids['rb'], 'p1', ids['q2'], [3])):
        pg.evaluate(PUT_JS, [f'/api/processors/{pid}/cvts/{box}/fiber-links/{key}',
                             {'cable': cable, 'strands': strands}])


def test_the_select_offers_another_boxs_opticalcon_while_it_has_free_strands(page):
    """P (B)'s Fiber section offers QUAD 1 (made on P (A)) and QUAD 2 (made
    on R (A)); picking QUAD 1 on OPT 1 and OPT 2 takes strands 3 and 4. R
    (B) is then offered QUAD 2 - one strand left after its OPT 1 takes 3 -
    and no longer QUAD 1, which is full; P (A) still shows QUAD 1 on both
    its rows."""
    pg, ids = page
    pid, pb, rb = ids['pid'], ids['pb'], ids['rb']
    rows = _rows(pg, pb)
    assert [r['role'] for r in rows] == ['OPT 1', 'OPT 2'], rows
    for r in rows:
        assert "QUAD 1 · 500'" in r['options'] and "QUAD 2 · 1000'" in r['options'], r
        assert "QUAD 3 · 300'" not in r['options'], r          # full: XD A and XD B hold all four
    for key, want in (('p1', [3]), ('p2', [4])):
        pg.locator(f'[data-lrd-field="fiber-link-cable-{pb}-{key}"]').select_option(ids['q1'])
        got = settled(pg, lambda key=key: (_box_links(_served(pg), pb) or {}).get(key),
                      lambda v, want=want: bool(v) and v.get('strands') == want, 8000)
        assert got == {'cable': ids['q1'], 'strands': want}, got
    rows = settled(pg, lambda: _rows(pg, pb), lambda rs: [r['value'] for r in rs] == [ids['q1'], ids['q1']])
    assert [r['value'] for r in rows] == [ids['q1'], ids['q1']], rows
    assert [r['chips'] for r in rows] == [['3 Green'], ['4 Brown']], rows
    rows = settled(pg, lambda: _rows(pg, rb), lambda rs: rs and "QUAD 1 · 500'" not in rs[0]['options'])
    assert "QUAD 1 · 500'" not in rows[0]['options'] and "QUAD 2 · 1000'" in rows[0]['options'], rows
    pg.locator(f'[data-lrd-field="fiber-link-cable-{rb}-p1"]').select_option(ids['q2'])
    got = settled(pg, lambda: (_box_links(_served(pg), rb) or {}).get('p1'), bool, 8000)
    assert got == {'cable': ids['q2'], 'strands': [3]}, got
    rows = _rows(pg, ids['pa'])
    assert [r['value'] for r in rows] == [ids['q1'], ids['q1']], rows
    assert "QUAD 1 · 500'" in rows[0]['options']
    assert pid and ids['errors'] == []


def test_the_binder_prints_each_links_strands_on_a_shared_quad(page):
    """Fiber connections: every link on a shared opticalCON prints its own
    strands, AT THE BREAKOUT in the same order with "crosses inside" (it
    crosses inside the cable, as an MTP does - no flip); the kind is said
    once. The strand map lists every box and input on the QUAD."""
    pg, ids = page
    _shared(pg, ids)
    out = settled(pg, lambda: pg.evaluate("""(ids) => {
        const app = window.app;
        const find = (id) => app._processorsResolved.find(p => p.id === id);
        const title = (id) => app._bBoxTitle(app._dockFindCvt(id).cvt);
        const rows = (id) => app._bFiberConnectionRows(find(id)).map(r => r.cells);
        const maps = (id) => app._bStrandMaps(find(id)).map(m => ({title: m.title, rows: m.rows.map(r => r.cells)}));
        return {h5: rows(ids.pid), sx: rows(ids.sx), maps: maps(ids.pid), sxMaps: maps(ids.sx),
                t: {pa: title(ids.pa), pb: title(ids.pb), ra: title(ids.ra), rb: title(ids.rb)}};
    }""", ids), lambda o: len(o['h5']) == 8 and o['h5'][6][1] == 'QUAD 2')
    t = out['t']
    assert out['h5'] == [
        ['SC1 · OPT 1', 'QUAD 1 (opticalCON QUAD)', '1 Blue', f"OPT 1 on {t['pa']}", '1 Blue · crosses inside'],
        ['SC1 · OPT 2', 'QUAD 1', '2 Orange', f"OPT 2 on {t['pa']}", '2 Orange · crosses inside'],
        ['SC1 · OPT 3', 'QUAD 1', '3 Green', f"OPT 1 on {t['pb']}", '3 Green · crosses inside'],
        ['SC1 · OPT 4', 'QUAD 1', '4 Brown', f"OPT 2 on {t['pb']}", '4 Brown · crosses inside'],
        ['SC2 · OPT 1', 'QUAD 2 (opticalCON QUAD)', '1 Blue', f"OPT 1 on {t['ra']}", '1 Blue · crosses inside'],
        ['SC2 · OPT 2', 'QUAD 2', '2 Orange', f"OPT 2 on {t['ra']}", '2 Orange · crosses inside'],
        ['SC2 · OPT 3', 'QUAD 2', '3 Green', f"OPT 1 on {t['rb']}", '3 Green · crosses inside'],
        ['SC2 · OPT 4', 'no fiber picked', '', f"OPT 2 on {t['rb']}", ''],
    ], out['h5']
    assert out['sx'][:3] == [
        ['trunk A', 'QUAD 3 (opticalCON QUAD)', '1 Blue · 2 Orange', 'X1 on Tessera XD A',
         '1 Blue · 2 Orange · crosses inside'],
        ['trunk B', 'QUAD 3', '3 Green · 4 Brown', 'X1 on Tessera XD B', '3 Green · 4 Brown · crosses inside'],
        ['trunk C', 'no fiber picked', '', 'X1 on Tessera XD C', ''],
    ], out['sx']
    maps = {m['title']: m['rows'] for m in out['maps']}
    assert maps["Strand map · QUAD 1 · opticalCON QUAD · 500'"] == [
        ['1 Blue', f"{t['pa']} · OPT 1"], ['2 Orange', f"{t['pa']} · OPT 2"],
        ['3 Green', f"{t['pb']} · OPT 1"], ['4 Brown', f"{t['pb']} · OPT 2"]], maps
    assert maps["Strand map · QUAD 2 · opticalCON QUAD · 1000'"] == [
        ['1 Blue', f"{t['ra']} · OPT 1"], ['2 Orange', f"{t['ra']} · OPT 2"],
        ['3 Green', f"{t['rb']} · OPT 1"], ['4 Brown', 'spare']], maps
    assert [m['rows'] for m in out['sxMaps']] == [[
        ['1 Blue', 'Tessera XD A · X1'], ['2 Orange', 'Tessera XD A · X1'],
        ['3 Green', 'Tessera XD B · X1'], ['4 Brown', 'Tessera XD B · X1']]], out['sxMaps']
    assert ids['errors'] == []


def test_the_pull_sheet_counts_a_shared_opticalcon_once(page):
    """QUAD 1 feeds four links on two boxes, QUAD 3 two XDs: each is ONE
    row, "opticalCON QUAD" with its length, under its name."""
    pg, ids = page
    _shared(pg, ids)
    out = settled(pg, lambda: pg.evaluate("""() => {
        const app = window.app;
        app._circuitTailCache = null;
        const list = JSON.parse(JSON.stringify(app.buildPullList()));
        return list.totals.map(r => [r.type, r.length, r.qty, r.label, r.notes]);
    }"""), lambda rows: len([r for r in rows if r[0] == 'opticalCON QUAD']) == 3)
    quads = sorted(r for r in out if r[0] == 'opticalCON QUAD')
    assert quads == [['opticalCON QUAD', "1000'", 1, 'QUAD 2', ''],
                     ['opticalCON QUAD', "300'", 1, 'QUAD 3', ''],
                     ['opticalCON QUAD', "500'", 1, 'QUAD 1', '']], out
    assert ids['errors'] == []
