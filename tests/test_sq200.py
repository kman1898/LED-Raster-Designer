"""Brompton's SQ200 -> QD-S -> XD rig.

The owner ruled the shape on 2026-09-28, on Brompton's datasheets plus his
answers:

* The SQ200's LED outputs are OUT 1 and OUT 2, two 100G QSFP28 ports, and
  each takes one QD-S - "so a max of 2 per SQ200". So the SQ200 is a
  two-slot unit whose slots are its OUT ports, and the QD-S is the card in
  one: twelve lettered 10G outputs, A-L, each feeding an XD, XD-S or XD-T
  ("up to 12 [XDs per QD-S] but with a max 10G capacity"). Behind a QD-S
  the XD-S and XD-T deliver all 12 of their ports; behind an SX40 only 10.
* A box on "output A of QD 1" is "QD 1 A" - its title the way an SX40's XD
  is "Tessera XD A". A name typed on the box still wins.
* EACH BOX IS CAPPED AT ITS 10G LINK: "The 5.25M pixels is right. the 12 is
  in case you dont max out each port on the unit then you have more
  bandwidth to be used on ports 11 and 12." 10 x the Brompton per-port
  capacity at the screen's bit depth and frame rate (ULL halves it), and
  over it is REFUSED - a placement, a drag, a fill, or a Processing change
  that would push a placed box over - never warned. Only on this rig.
* Loops, provisional "at least until we can verify with a manual": one
  QD-S loops A to B on the same unit ("if you jsut use one 100g then A
  loops to B on the same unit"); two loop QD 1 X to QD 2 X ("with dual
  100G then Box 1 A loops to Box 2 A").
* "Backup SQ200 is handled with the second port on the QDs": the backup
  processor feeds each QD-S's IN 2, and the XDs keep their X1 alone.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_sq200.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

# Where the tray render for the owner lands, only where a folder is named.
SHOTS = os.environ.get('LRD_SQ200_SHOT_DIR')

QD = 'brompton-card-qd-s'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── helpers ──────────────────────────────────────────────────────────────

def _ok(resp, code=200):
    assert resp.status_code == code, resp.get_data(as_text=True)[:400]
    return resp.get_json()


def _refused(resp, code=400):
    assert resp.status_code == code, resp.get_data(as_text=True)[:400]
    return resp.get_json()['error']


def _state(client):
    return client.get('/api/processors').get_json()


def _res_proc(client, pid):
    return next(p for p in _state(client)['resolved'] if p['id'] == pid)


def _res_card(client, pid, index=0):
    return next(s['card'] for s in _res_proc(client, pid)['slots']
                if s['index'] == index)


def _sq200(client, qds=1, name=''):
    """An SQ200 with `qds` QD-S fitted, OUT 1 first. -> (pid, [card ids])."""
    st = _ok(client.post('/api/processors',
                         json={'deviceId': 'brompton-sq200', 'name': name}),
             201)
    pid = st['processors'][-1]['id']
    cards = []
    for index in range(qds):
        st = _ok(client.put(f'/api/processors/{pid}/slots/{index}',
                            json={'deviceId': QD}))
        proc = next(p for p in st['processors'] if p['id'] == pid)
        cards.append(proc['slots'][index]['card']['id'])
    return pid, cards


def _boxes(client, pid, cid, n, device='brompton-xd-s'):
    """Put `n` boxes on one QD-S, lowest free output first. -> box ids."""
    for _ in range(n):
        _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                        json={'deviceId': device}), 201)
    card = next(s['card'] for s in _res_proc(client, pid)['slots']
                if s['card'] and s['card']['id'] == cid)
    return [b['id'] for b in card['cvts']]


def _screen(name, pixels, bit_depth=8, frame_rate=60, ull=False):
    """One screen as the client sends it where a link cap is in play: its
    ports, and the pixels each carries with the settings they are read at."""
    return {'layerId': name, 'name': name, 'ports': len(pixels),
            'platform': 'brompton', 'portPixels': list(pixels),
            'bitDepth': bit_depth, 'frameRate': frame_rate,
            'lowLatency': ull}


def _fill(client, card, screens, layer='Main', **window):
    body = dict({'layerId': layer, 'cardId': card, 'screens': screens},
                **window)
    return client.post('/api/port-assignments/place-overflow', json=body)


def _pins(client):
    return (client.get('/api/project').get_json()
            .get('port_assignments') or {}).get('pins') or []


# ── A. the shape ─────────────────────────────────────────────────────────

def test_an_xd_s_on_a_qd_s_output_delivers_all_12_ports(client):
    """SQ200 + one QD-S + an XD-S on output A: 12 sockets, 1-12 on the box's
    face, all of them the card's - behind an SX40 the same box gives 10."""
    pid, (cid,) = _sq200(client)
    card = _res_card(client, pid)
    assert (card['unitTitle'], card['trunks'], card['portsPerTrunk'],
            card['boxFed'], card['cvts']) == ('QD 1', 12, 12, True, [])
    assert card['defaultCvt'] == 'brompton-xd-s'
    (box,) = _boxes(client, pid, cid, 1)
    card = _res_card(client, pid)
    xd = card['cvts'][0]
    assert xd['id'] == box and xd['portCount'] == 12
    assert [p['localNumber'] for p in xd['ports']] == list(range(1, 13))
    assert [p['number'] for p in card['ports']] == list(range(1, 13))
    assert _res_proc(client, pid)['defined'] == 12
    # the plain XD has ten on the same output letter's twin
    _boxes(client, pid, cid, 1, 'brompton-xd')
    card = _res_card(client, pid)
    assert [b['portCount'] for b in card['cvts']] == [12, 10]


def test_two_qd_s_at_most_and_nothing_else_on_an_out_port(client):
    """"so a max of 2 per SQ200": OUT 1 and OUT 2 each take one QD-S, and
    a third has nowhere to go - refused with the reason, nothing stored.
    An SQ200's output takes nothing but a QD-S, and a QD-S goes nowhere
    but an SQ200."""
    pid, cards = _sq200(client, qds=2)
    assert len(cards) == 2
    why = _refused(client.put(f'/api/processors/{pid}/slots/2',
                              json={'deviceId': QD}))
    assert why == ('Tessera SQ200 has 2 outputs, OUT 1 and OUT 2, and each '
                   'takes one Tessera QD-S - there is no place for another.')
    assert len([s for s in _res_proc(client, pid)['slots'] if s['card']]) == 2
    why = _refused(client.put(f'/api/processors/{pid}/slots/0',
                              json={'deviceId': 'novastar-card-h-4xfiber'}))
    assert 'does not go in Tessera SQ200' in why
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}),
             201)
    h9 = st['processors'][-1]['id']
    why = _refused(client.put(f'/api/processors/{h9}/slots/0',
                              json={'deviceId': QD}))
    assert why == 'Tessera QD-S does not go in H9.'


def test_boxes_are_named_by_qd_s_and_letter_and_a_typed_name_wins(client):
    """"QD 1" on OUT 1 and "QD 2" on OUT 2; the box on output C of QD 2 is
    "QD 2 C" - on its header and wherever paper names where it hangs."""
    pid, (one, two) = _sq200(client, qds=2)
    a = _boxes(client, pid, one, 1)[0]
    two_boxes = _boxes(client, pid, two, 3)
    assert _res_card(client, pid, 0)['cvts'][0]['displayTitle'] == 'QD 1 A'
    card = _res_card(client, pid, 1)
    assert card['unitTitle'] == 'QD 2'
    assert [(b['displayTitle'], b['trunkTitle']) for b in card['cvts']] == \
        [('QD 2 A', 'QD 2 A'), ('QD 2 B', 'QD 2 B'), ('QD 2 C', 'QD 2 C')]
    _ok(client.put(f'/api/processors/{pid}/cvts/{two_boxes[2]}',
                   json={'name': 'USL'}))
    card = _res_card(client, pid, 1)
    assert (card['cvts'][2]['displayTitle'], card['cvts'][2]['trunkTitle']) \
        == ('USL', 'QD 2 C')
    assert _res_card(client, pid, 0)['cvts'][0]['id'] == a


def test_the_qd_s_is_never_offered_or_taken_as_a_box(client):
    """The QD-S is the SQ200's card now. Its old box entry stays only so a
    saved file opens: a box picker never offers it (catalog `legacy`) and a
    POST naming it is refused on any card."""
    pid, (cid,) = _sq200(client)
    why = _refused(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                               json={'deviceId': 'brompton-qd-s'}))
    assert 'not a breakout box' in why
    st = _ok(client.post('/api/processors',
                         json={'deviceId': 'brompton-sx40'}), 201)
    sx = st['processors'][-1]
    sx_card = sx['slots'][0]['card']['id']
    why = _refused(client.post(
        f'/api/processors/{sx["id"]}/cards/{sx_card}/cvts',
        json={'deviceId': 'brompton-qd-s'}))
    assert 'not a breakout box' in why
    assert catalog.get_device('brompton-qd-s')['legacy'] is True


# ── B. the link cap ──────────────────────────────────────────────────────

def test_a_fill_that_pushes_a_box_past_its_10g_link_is_refused(client):
    """12 ports at 500,000 px is 6M on one XD-S - over its 10G link's
    5.25M at 8-bit 60 Hz. The fill is refused, the box named with what to
    do, and nothing is written."""
    pid, (cid,) = _sq200(client)
    _boxes(client, pid, cid, 1)
    resp = _fill(client, cid, [_screen('Main', [500_000] * 12)])
    why = _refused(resp, 409)
    assert why == ('QD 1 A carries 6M px - over its 10G link\'s 5.25M at '
                   '8-bit 60 Hz. Lower the frame rate or bit depth.')
    assert resp.get_json()['linkCap'] is True
    assert _pins(client) == []


def test_a_placement_just_under_the_cap_goes_on_and_one_more_is_refused(
        client):
    """10 ports x 525,000 = 5.25M sits exactly on the cap and lands (100%
    is a good link). The spare 11th socket takes a port only while the
    link has room: 1,000 px more is refused, one socket at a time too -
    and where the two figures would round alike they are said in full."""
    pid, (cid,) = _sq200(client)
    _boxes(client, pid, cid, 1)
    screens = [_screen('Main', [525_000] * 10),
               _screen('Side', [1_000, 1_000])]
    _ok(_fill(client, cid, screens))
    assert len(_pins(client)) == 10
    resp = client.post('/api/port-assignments/place', json={
        'layerId': 'Side', 'index': 0, 'cardId': cid, 'port': 11,
        'screens': screens})
    why = _refused(resp, 409)
    assert why.startswith('QD 1 A carries 5,251,000 px - over its 10G '
                          'link\'s 5,250,000 at 8-bit 60 Hz.'), why
    assert len(_pins(client)) == 10
    # released, the same socket takes it
    _ok(client.post('/api/port-assignments/unpin',
                    json={'layerId': 'Main', 'index': 9,
                          'screens': screens}))
    _ok(client.post('/api/port-assignments/place', json={
        'layerId': 'Side', 'index': 0, 'cardId': cid, 'port': 11,
        'screens': screens}))


def test_a_bit_depth_change_that_pushes_a_placed_box_over_is_refused(client):
    """12 x 400,000 = 4.8M fits at 8-bit 60 Hz (5.25M). At 10-bit the link
    carries 4.2M, so the change is refused and the setting stays as it was;
    ULL at 8-bit halves the cap to 2.62M and is refused too. At 50 Hz the
    link carries 6.3M and the check passes - and a check never writes."""
    pid, (cid,) = _sq200(client)
    _boxes(client, pid, cid, 1)
    now = [_screen('Main', [400_000] * 12)]
    _ok(_fill(client, cid, now))
    check = lambda after: client.post(  # noqa: E731
        '/api/port-assignments/link-check',
        json={'before': now, 'screens': after})
    why = _refused(check([_screen('Main', [400_000] * 12, bit_depth=10)]), 409)
    assert why == ('QD 1 A carries 4.8M px - over its 10G link\'s 4.2M at '
                   '10-bit 60 Hz. Lower the frame rate or bit depth.')
    why = _refused(check([_screen('Main', [400_000] * 12, ull=True)]), 409)
    assert 'over its 10G link\'s 2.62M at 8-bit 60 Hz ULL' in why, why
    assert _ok(check([_screen('Main', [400_000] * 12, frame_rate=50)])) \
        == {'ok': True}
    assert len(_pins(client)) == 12, 'a check wrote something'


def test_an_sx40_rig_has_no_link_cap(client):
    """The owner ruled the cap on the QD-S rig only: an SX40's XD takes 10
    ports at 600,000 px (6M) as it always did."""
    st = _ok(client.post('/api/processors',
                         json={'deviceId': 'brompton-sx40'}), 201)
    card = st['processors'][-1]['slots'][0]['card']['id']
    _ok(_fill(client, card, [_screen('Main', [600_000] * 10)]))
    assert len(_pins(client)) == 10
    box = st['resolved'][-1]['slots'][0]['card']['cvts'][0]
    assert box['linkCapPorts'] is None


# ── C. loops ─────────────────────────────────────────────────────────────

def test_one_qd_s_loops_a_to_b_on_the_same_unit(client):
    """"if you jsut use one 100g then A loops to B on the same unit": with
    redundancy on, B is A's loop end - its own box (backupOf A), each
    socket carrying the return of the same socket on A - and so on to K
    and L. One On/Off switch: the SX40's per-pair picks are refused."""
    pid, (cid,) = _sq200(client)
    boxes = _boxes(client, pid, cid, 4)
    _ok(client.put(f'/api/processors/{pid}', json={'redundancy': True}))
    card = _res_card(client, pid)
    assert [b['backupOf'] for b in card['cvts']] == \
        [None, boxes[0], None, boxes[2]]
    ports = {p['number']: p for p in card['ports']}
    assert ports[13]['backsUp']['boxTitle'] == 'QD 1 A'
    assert ports[1]['backedBy']['boxTitle'] == 'QD 1 B'
    proc = _res_proc(client, pid)
    assert proc['redundancyPairing']['short'] == 'Loops A to B … K to L'
    assert proc['redundancyPairing']['provisional'] is True
    why = _refused(client.put(f'/api/processors/{pid}',
                              json={'redundancyPairs': ['A']}))
    assert 'on or off' in why


def test_two_qd_s_loop_qd_1_to_qd_2_letter_for_letter(client):
    """"with dual 100G then Box 1 A loops to Box 2 A": QD 2 A is QD 1 A's
    loop end, and nothing pairs inside either QD-S - QD 1 B is a primary."""
    pid, (one, two) = _sq200(client, qds=2)
    near = _boxes(client, pid, one, 2)
    far = _boxes(client, pid, two, 2)
    _ok(client.put(f'/api/processors/{pid}', json={'redundancy': True}))
    c1, c2 = _res_card(client, pid, 0), _res_card(client, pid, 1)
    assert [b['backupOf'] for b in c1['cvts']] == [None, None]
    assert [b['backupOf'] for b in c2['cvts']] == near
    assert c2['backupFor']['title'] == 'QD 1'
    p1 = {p['number']: p for p in c1['ports']}
    assert p1[1]['backedBy']['cardId'] == two
    assert p1[13]['backedBy']['boxTitle'] == 'QD 2 B'
    assert all(p.get('backsUp') for p in c2['ports'])
    assert c1['redundancyShape']['usable'] == 144
    assert c2['redundancyShape']['usable'] == 0
    proc = _res_proc(client, pid)
    assert proc['redundancyPairing']['short'] == 'Loops QD 1 to QD 2'
    assert proc['redundancyPairing']['pairs'][0] == {
        'primary': 'QD 1 A', 'backup': 'QD 2 A'}
    # a fill on QD 2 has nowhere to land - every socket is a return
    why = _refused(_fill(client, two, [_screen('Main', [1_000] * 4)]), 409)
    assert 'no free ports' in why
    assert far


# ── D. the backup SQ200 ──────────────────────────────────────────────────

def test_the_backup_sq200_feeds_qd_s_in_2_and_the_xds_keep_x1(client):
    """"Backup SQ200 is handled with the second port on the QDs": with the
    backup processor on, each QD-S takes IN 2 beside IN 1 and its XDs keep
    their X1 alone - nothing binds to an XD's X2, and no twin box is
    counted for the backup."""
    pid, (cid,) = _sq200(client, name='SQ A')
    (box,) = _boxes(client, pid, cid, 1)
    card = _res_card(client, pid)
    assert card['fiberLinkKeys'] == ['p1']
    assert card['linkTitles'] == {'p1': 'IN 1', 'b1': 'IN 2'}
    _ok(client.put(f'/api/processors/{pid}', json={'backupUnit': {}}))
    proc = _res_proc(client, pid)
    card = proc['slots'][0]['card']
    assert (card['fiberLinkKeys'], card['backupInputs']) == (['p1', 'b1'], True)
    xd = card['cvts'][0]
    assert (xd['fiberLinkKeys'], xd['backupInputs']) == (['p1'], False)
    assert proc['backupUnit'] == {'name': 'SQ A BU', 'typedName': '',
                                  'boxes': []}
    # IN 1 and IN 2 take their fiber at the QD-S's own URL
    st = _ok(client.post('/api/fiber-cables',
                         json={'kind': 'tac', 'strands': 12, 'ft': 300}), 201)
    tac = st['fiberCables'][-1]['id']
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}/fiber-links/p1',
                   json={'cable': tac}))
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}/fiber-links/b1',
                   json={}))
    card = _res_card(client, pid)
    assert card['fiberLinks'] == {'p1': {'cable': tac, 'strands': [1, 2]},
                                  'b1': {'cable': tac, 'strands': [3, 4]}}
    why = _refused(client.put(
        f'/api/processors/{pid}/cvts/{box}/fiber-links/b1',
        json={'cable': tac}))
    assert 'has no link X2' in why
    # off: IN 2's link goes with the backup processor
    _ok(client.put(f'/api/processors/{pid}', json={'backupUnit': None}))
    assert _res_card(client, pid)['fiberLinks'] == {
        'p1': {'cable': tac, 'strands': [1, 2]}}


# ── E. a file from before ────────────────────────────────────────────────

def test_a_file_with_a_qd_s_as_a_box_still_loads(client):
    """Before 2026-09-28 the QD-S was a box, and a file may carry one - on
    an SX40, from before the rate fix. It opens: the box resolves as it
    always did, nothing crashes, and it cannot be added again."""
    st = _ok(client.post('/api/processors',
                         json={'deviceId': 'brompton-sx40'}), 201)
    project = client.get('/api/project').get_json()
    card = project['processors'][-1]['slots'][0]['card']
    card['cvts'][1] = {'id': 'cvt900', 'deviceId': 'brompton-qd-s',
                       'name': '', 'mode': 'default'}
    _ok(client.put('/api/project', json=project))
    state = _state(client)
    boxes = state['resolved'][-1]['slots'][0]['card']['cvts']
    legacy = next(b for b in boxes if b['id'] == 'cvt900')
    assert legacy['deviceName'] == 'Tessera QD-S'
    assert legacy['displayTitle'] == 'Tessera QD-S B'
    assert st['processors'][-1]['id'] == state['processors'][-1]['id']


def test_an_sq200_saved_as_a_one_box_unit_opens_with_its_two_outputs(client):
    """Before 2026-09-28 an SQ200 was a one-box unit - one fixed card of its
    own model, no port, no box. It opens as the two-output unit it is now:
    OUT 1 and OUT 2 empty, its name and redundancy kept, a hand pin that
    pointed at the old card reported (Release offered), never moved."""
    wall = _ok(client.post('/api/layer/add', json={
        'name': 'Main', 'columns': 2, 'rows': 2, 'cabinet_width': 100,
        'cabinet_height': 100}))
    main = str(wall['id'])
    project = client.get('/api/project').get_json()
    project['processors'] = [{
        'id': 'proc7', 'deviceId': 'brompton-sq200', 'name': 'SQ OLD',
        'mode': None, 'redundancy': True, 'pairingsPerCard': True,
        'slots': [{'index': 0, 'card': {
            'id': 'card7f', 'deviceId': 'brompton-sq200', 'name': '',
            'mode': 'default', 'fixed': True, 'cvts': []}}]}]
    project['port_assignments'] = {
        'auto': False, 'autoRetired': True,
        'pins': [{'layerId': main, 'index': 0, 'cardId': 'card7f',
                  'port': 6}]}
    _ok(client.put('/api/project', json=project))
    proc = _state(client)['resolved'][0]
    assert (proc['name'], proc['redundancy']) == ('SQ OLD', True)
    assert [(s['name'], s['card']) for s in proc['slots']] == \
        [('OUT 1', None), ('OUT 2', None)]
    res = client.post('/api/port-assignments/resolve', json={
        'screens': [_screen(main, [1_000])]}).get_json()['resolution']
    assert [i['kind'] for i in res['issues']] == ['pin-card-gone']
    # and it takes its QD-S like any SQ200
    _ok(client.put('/api/processors/proc7/slots/1', json={'deviceId': QD}))
    assert _res_card(client, 'proc7', 1)['unitTitle'] == 'QD 2'


# ── F. the tray ──────────────────────────────────────────────────────────

SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 10, rows: 13,
                                                     cabinet_width: 200, cabinet_height: 200});
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'brompton', bitDepth: 8,
                                             frameRate: 60});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('sq200_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app._processorRequest('/api/processors', 'POST',
                                {deviceId: 'brompton-sq200', name: 'SQ A'}, 'Add Processor');
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('SQ200 Seed');
    const sq = app._processorsResolved[0];
    return {sq: sq.id, wall: wall.id};
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
    pg.wait_for_timeout(1000)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _card_id(pg, sq, index=0):
    return pg.evaluate("""([sq, i]) => {
        const p = window.app._processorsResolved.find(x => x.id === sq);
        const s = p && p.slots.find(x => x.index === i);
        return s && s.card ? s.card.id : null;
    }""", [sq, index])


def test_the_tray_adds_a_qd_s_and_an_xd_s_and_names_it_qd_1_a(page):
    """Add an SQ200, "+ QD-S" on its strip, "+ Box" and the XD-S (the
    QD-S's default, first in the list): the box reads "QD 1 A" in the
    tray. A second XD-S reads "QD 1 B"."""
    pg, ids = page
    sq = ids['sq']
    add_unit = pg.locator(f'[data-lrd-field="dock-addunit-{sq}"]')
    assert add_unit.text_content() == '+ QD-S'
    add_unit.click()
    pg.wait_for_timeout(900)
    card = _card_id(pg, sq)
    assert card, 'no QD-S went on OUT 1'
    assert pg.evaluate('() => window.app.history[window.app.historyIndex].action') \
        == 'Add QD-S'
    # A QD-S has no port outside a box (box-fed), so the add opens its box
    # picker on its own - the "+ Box" list (owner, 2026-10-04: "throw up a
    # dialog asking you to add them"). No click on "+ Box" first: that
    # would toggle the open list shut.
    assert pg.evaluate('() => window.app._hwPopover && window.app._hwPopover.id') \
        == f'addbox-{card}'
    items = pg.evaluate("""() => [...document.querySelectorAll(
        '.hw-dock-addbox-menu .hw-dock-addbox-item')].map(b => b.textContent)""")
    assert items == ['Tessera XD-S', 'Tessera XD', 'Tessera XD-T'], items
    pg.locator(f'[data-lrd-field="dock-addbox-{card}-brompton-xd-s"]').click()
    pg.wait_for_timeout(900)
    names = """(card) => {
        const c = window.app._dockFindCard(card).card;
        return c.cvts.map(b => {
            const f = document.querySelector(`[data-lrd-field="processor-cvt-name-${b.id}"]`);
            return f ? f.placeholder : null;
        });
    }"""
    assert pg.evaluate(names, card) == ['QD 1 A']
    pg.locator(f'[data-lrd-field="dock-addbox-{card}"]').click()
    pg.wait_for_timeout(300)
    pg.locator(f'[data-lrd-field="dock-addbox-{card}-brompton-xd-s"]').click()
    pg.wait_for_timeout(900)
    assert pg.evaluate(names, card) == ['QD 1 A', 'QD 1 B']
    head = pg.evaluate("""(card) => {
        const row = document.querySelector(`[data-hwdock="card-${card}"]`);
        return row ? row.textContent : '';
    }""", card)
    assert 'QD 1 · Tessera QD-S' in head, head
    if SHOTS:
        # The tray is only as tall as the user dragged it; the render for
        # the owner opens it far enough to show the whole unit.
        tray = "(h) => h ? document.getElementById('hardware-dock').style" \
            ".setProperty('--lrd-dock-h', h) : document.getElementById(" \
            "'hardware-dock').style.removeProperty('--lrd-dock-h')"
        pg.evaluate(tray, '640px')
        pg.wait_for_timeout(500)
        os.makedirs(SHOTS, exist_ok=True)
        pg.locator(f'[data-lrd-field="processor-name-{sq}"]').locator(
            'xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), '
            '" hw-dock-proc ")][1]').screenshot(
            path=os.path.join(SHOTS, 'sq200-tray.png'))
        pg.evaluate(tray, '')
    assert ids['errors'] == []


def test_a_bit_depth_change_over_the_link_is_refused_in_the_panel(page):
    """The wall fills QD 1 A at 8-bit 60 Hz (4.8M of 5.25M). Picking 10-bit
    would push it past the link's 4.2M: the change is refused, the layer
    and the control keep 8, the status line says why, and no history entry
    is made. 50 Hz goes through."""
    pg, ids = page
    sq, wall = ids['sq'], ids['wall']
    card = _card_id(pg, sq)
    first = pg.evaluate("""(card) => window.app._dockFindCard(card).card.cvts[0].ports[0].number""",
                        card)
    pg.evaluate("""async ([wall, card, first]) => {
        const app = window.app;
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
            {layerId: String(wall), cardId: card, firstPort: first, lastPort: first + 11},
            null, 'Fill Ports In Order');
    }""", [wall, card, first])
    pg.wait_for_timeout(600)
    placed = pg.evaluate("""(wall) => (window.app.project.port_assignments.pins || [])
        .filter(p => p.layerId === String(wall)).length""", wall)
    assert placed == 12, placed
    before = pg.evaluate('() => window.app.historyIndex')
    pg.evaluate("""() => {
        const s = document.getElementById('bit-depth');
        s.value = '10';
        s.dispatchEvent(new Event('change'));
    }""")
    pg.wait_for_timeout(900)
    out = pg.evaluate("""() => ({
        layer: window.app.project.layers[0].bitDepth,
        control: document.getElementById('bit-depth').value,
        status: document.getElementById('status-message').textContent,
        index: window.app.historyIndex,
    })""")
    assert out['layer'] == 8 and out['control'] == '8', out
    assert out['status'].startswith('QD 1 A carries ') \
        and "over its 10G link's 4.2M at 10-bit 60 Hz" in out['status'], out
    assert out['index'] == before
    pg.evaluate("""() => {
        const s = document.getElementById('frame-rate');
        s.value = '50';
        s.dispatchEvent(new Event('change'));
    }""")
    pg.wait_for_timeout(900)
    assert pg.evaluate('() => window.app.project.layers[0].frameRate') == 50
    assert ids['errors'] == []


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


def test_the_gear_names_the_outputs_and_the_qd_s_sheet_lists_in_1_and_in_2(
        page):
    """The SQ200's ⚙ names its slots as its face does - OUT 1, OUT 2 - with
    one Off · On redundancy bar (the loop form follows the QD-S count) and
    the BACKUP PROCESSOR switch; with the backup on, the QD-S's ≡ sheet is
    its Fiber section: IN 1, and IN 2 for the backup SQ200."""
    pg, ids = page
    sq = ids['sq']
    card = _card_id(pg, sq)
    assert pg.evaluate(OPEN_GEAR_JS, f'proc-{sq}')
    pg.wait_for_timeout(300)
    bar_sel = f'#hw-gear-popover [data-lrd-field="processor-redundancy-{sq}"]'
    gear = pg.evaluate("""(sel) => ({
        text: document.getElementById('hw-gear-popover').textContent,
        bar: [...document.querySelectorAll(sel + ' button')].map(b => b.textContent),
    })""", bar_sel)
    assert 'OUT 1' in gear['text'] and 'OUT 2' in gear['text'], gear
    assert gear['bar'] == ['Off', 'On'], gear
    pg.locator(bar_sel + ' [data-level="on"]').click()
    pg.wait_for_timeout(900)
    assert pg.evaluate(OPEN_GEAR_JS, f'proc-{sq}')
    pg.wait_for_timeout(300)
    fact = pg.locator('#hw-gear-popover .hw-pop-red-fact').text_content()
    assert fact.startswith('QD 1 loops in pairs: A to B') \
        and 'Provisional' in fact, fact
    pg.locator(f'#hw-gear-popover [data-lrd-field="processor-backup-{sq}"] '
               '[data-level="on"]').click()
    pg.wait_for_timeout(900)
    pg.keyboard.press('Escape')
    pg.locator(f'[data-lrd-field="data-cable-sheet-{card}"]').click()
    pg.wait_for_timeout(700)
    rows = pg.evaluate("""(card) => [...document.querySelectorAll(
        `[data-lrd-cable-sheet="card:${card}"] [data-lrd-fiber-link]`)].map(r => [
            r.dataset.lrdFiberLink, r.querySelector('.hw-dock-fiber-role').textContent])""",
                       card)
    assert rows == [[f'{card}:p1', 'IN 1'], [f'{card}:b1', 'IN 2']], rows
    pill = pg.evaluate("""(card) => {
        const row = document.querySelector(`[data-hwdock="card-${card}"]`);
        const own = row && row.querySelector(':scope > .hw-dock-redpill');
        return own ? own.textContent : null;
    }""", card)
    assert pill == 'Loops A to B … K to L', pill
    if SHOTS:
        pg.locator(f'[data-lrd-cable-sheet="card:{card}"]').screenshot(
            path=os.path.join(SHOTS, 'sq200-qd-s-fiber.png'))
    pg.locator(f'[data-lrd-field="data-cable-sheet-{card}"]').click()
    pg.wait_for_timeout(500)
    # The pull sheet counts the QD-S as gear - its own 1U unit - under its
    # title, beside the SQ200 and its backup; the backup brings no QD-S.
    rows = pg.evaluate("""(sq) => {
        const hw = (window.app.buildPullList().hardware || [])
            .find(h => h.kind === 'processor' && h.id === sq);
        return hw ? hw.rows.map(r => [r.type, r.label]) : null;
    }""", sq)
    assert ['Tessera QD-S', 'QD 1'] in rows, rows
    assert ['Tessera SQ200', 'SQ A, SQ A BU (backup)'] in rows, rows
    assert ['Tessera XD-S', 'QD 1 A, QD 1 B'] in rows, rows
    assert sum(1 for r in rows if r[0] == 'Tessera QD-S') == 1, rows
    # The binder prints the rig, naming the boxes by QD-S and letter.
    texts = pg.evaluate("""() => {
        const app = window.app;
        const records = app.renderBinderPages(app.readBinderOptions(), {bitmaps: false});
        return JSON.stringify(records.map(r => r.ops));
    }""")
    assert 'QD 1 A' in texts and 'QD 1 B' in texts
    assert ids['errors'] == []
