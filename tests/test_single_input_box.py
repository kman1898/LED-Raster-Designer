"""A CVT4K-S on ONE OPT: the box's input switch.

The owner (2026-09-26): "it is technically possible on a UHD Junior that
has four optical ports that I use for CVT 4K's. And each one only uses one
optical port." On one OPT the box carries only that OPT's share - on a UHD
Jr OPT 1 = Ethernet 1-8, OPT 2 = 9-16, OPT 3/4 copies of them - so it
drives 8 of its 16 outputs (fewer where the trunk carries fewer). How the
app knows: "A switch on the box" - the box record's `inputs: 1`, absent
meaning the nameplate's two.

Only the CVT4K-S's catalog entry documents it (singleInput); every other
box is untouched. A single-input box takes one trunk (trunks used / free,
the add check, the resolver's blocks and copies), has one primary link
(OPT 1) and one backup input (OPT 3), and is what "+ Box" and the gear's
picker offer as "CVT4K-S (1 OPT)" where one trunk is free.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_single_input_box.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

SCRATCH = os.environ.get('LRD_ONE_OPT_DIR')

CVT4K = 'novastar-cvt4k-s'
UHD_JR = 'novastar-novapro-uhd-jr'
VX1000 = 'novastar-vx1000'
H4 = 'novastar-card-h-4xfiber'
H4E = 'novastar-card-h-4xfiber-enhanced'


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


def _unit(client, device_id):
    """An all-in-one unit: its id and its fixed card's id."""
    st = _ok(client.post('/api/processors', json={'deviceId': device_id}), 201)
    proc = st['processors'][-1]
    return proc['id'], proc['slots'][0]['card']['id']


def _h9(client, card):
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': card}))
    proc = next(p for p in st['processors'] if p['id'] == pid)
    return pid, proc['slots'][0]['card']['id']


def _add(client, pid, cid, device=CVT4K, **extra):
    return client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                       json=dict(deviceId=device, pair=False, **extra))


def _res_card(client, cid):
    for proc in _state(client)['resolved']:
        for slot in proc['slots']:
            if (slot.get('card') or {}).get('id') == cid:
                return slot['card']
    raise AssertionError(f'no card {cid}')


def _raw_box(client, box_id):
    for proc in _state(client)['processors']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == box_id:
                    return box
    return None


def _set_inputs(client, pid, box_id, n):
    return client.put(f'/api/processors/{pid}/cvts/{box_id}', json={'inputs': n})


def _span(box):
    nums = [p['number'] for p in box['ports']]
    return (min(nums), max(nums)) if nums else None


# ── the catalog ──────────────────────────────────────────────────────────

def test_only_the_cvt4k_s_documents_one_input():
    """The no-assumptions rule: the option is the CVT4K-S's, read off its
    catalog entry, and no other box grows one."""
    with_it = [d['id'] for d in catalog.devices('cvt') if d.get('singleInput')]
    assert with_it == [CVT4K], with_it
    box = catalog.get_device(CVT4K)
    assert box['singleInput'] == {'ports': 8}
    assert catalog.trunks_in(box) == 2, 'trunks_in keeps the nameplate'
    assert catalog.box_inputs_allowed(box) == (1, 2)
    assert catalog.box_inputs_allowed(catalog.get_device('novastar-cvt10')) == (1,)
    assert catalog.box_trunks_in({'inputs': 1}, box) == 1
    assert catalog.box_trunks_in({}, box) == 2
    assert catalog.box_trunks_in({'inputs': True}, box) == 2
    # a stored 1 on a box without the option changes nothing
    xd = catalog.get_device('brompton-tessera-xd')
    assert catalog.box_trunks_in({'inputs': 1}, xd) == catalog.trunks_in(xd)


# ── ports and trunks ─────────────────────────────────────────────────────

def test_four_single_input_boxes_on_a_uhd_jr_are_1_8_9_16_and_their_copies(client):
    """Four CVT4K-S, one per OPT: OPT 1 = card ports 1-8, OPT 2 = 9-16,
    OPT 3 and 4 copies of them - all four OPTs used, 8 sockets a box."""
    pid, cid = _unit(client, UHD_JR)
    for _ in range(4):
        _ok(_add(client, pid, cid, inputs=1), 201)
    card = _res_card(client, cid)
    assert (card['trunksUsed'], card['trunksFree']) == (4, 0), card
    boxes = card['cvts']
    assert [b['trunkIndex'] for b in boxes] == [0, 1, 2, 3]
    assert [b['trunksIn'] for b in boxes] == [1, 1, 1, 1]
    assert [b['portCount'] for b in boxes] == [8, 8, 8, 8]
    assert [b['firstPort'] for b in boxes] == [1, 9, 1, 9]
    assert [_span(b) for b in boxes] == [(1, 8), (9, 16), (1, 8), (9, 16)]
    ids = [b['id'] for b in boxes]
    assert [b['duplicateOf'] for b in boxes] == [None, None, ids[0], ids[1]]
    assert [b['trunkLetter'] for b in boxes] == ['A', 'B', 'C', 'D']
    assert all(_raw_box(client, i)['inputs'] == 1 for i in ids)
    # a fifth has nothing to plug into, on one input or two
    assert 'All 4 trunks' in _refused(_add(client, pid, cid, inputs=1))
    assert 'All 4 trunks' in _refused(_add(client, pid, cid))


def test_a_vx1000_takes_one_and_gets_8_of_its_10(client):
    """The VX1000's one OPT carries 10, and a single-input CVT4K-S delivers
    its own 8 of them: min(8, 10)."""
    pid, cid = _unit(client, VX1000)
    _refused(_add(client, pid, cid))          # 2 OPT does not fit 1 trunk
    _ok(_add(client, pid, cid, inputs=1), 201)
    card = _res_card(client, cid)
    (box,) = card['cvts']
    assert (box['trunksIn'], box['portCount'], _span(box)) == (1, 8, (1, 8))
    assert (card['trunksUsed'], card['trunksFree']) == (1, 0)


def test_the_enhanced_h_card_gives_8_not_10_on_one_input(client):
    """10 per trunk on the enhanced H_4xfiber: one OPT still gets the box's
    own one-input share, 8 - and four of them read short of the card's 40."""
    pid, cid = _h9(client, H4E)
    for _ in range(4):
        _ok(_add(client, pid, cid, inputs=1), 201)
    card = _res_card(client, cid)
    assert [b['portCount'] for b in card['cvts']] == [8, 8, 8, 8]
    assert [b['firstPort'] for b in card['cvts']] == [1, 11, 21, 31]
    assert card['shortfall']['delivered'] == 32 and card['shortfall']['ceiling'] == 40


def test_a_cvt10_is_unaffected(client):
    """inputs means nothing on a box without the option: 1 is its nameplate
    (accepted, nothing stored), 2 is refused, and it still delivers 8 on an
    8-per-trunk card, one trunk a box."""
    pid, cid = _unit(client, UHD_JR)
    st = _ok(_add(client, pid, cid, 'novastar-cvt10', inputs=1), 201)
    box_id = st['processors'][-1]['slots'][0]['card']['cvts'][0]['id']
    assert 'inputs' not in _raw_box(client, box_id)
    assert 'runs on 1 OPT' in _refused(_add(client, pid, cid, 'novastar-cvt10', inputs=2))
    assert 'runs on 1 OPT' in _refused(_set_inputs(client, pid, box_id, 2))
    _ok(_set_inputs(client, pid, box_id, 1))
    assert 'inputs' not in _raw_box(client, box_id)
    card = _res_card(client, cid)
    (box,) = card['cvts']
    assert (box['trunksIn'], box['portCount'], box['singleInput']) == (1, 8, False)
    assert box['fiberLinkKeys'] == ['p1']


# ── the switch ───────────────────────────────────────────────────────────

def test_the_switch_round_trips_and_undo_puts_it_back(client):
    """2 to 1: 16 sockets become 8 and a trunk comes free; 1 to 2 gives
    them back. The whole-project PUT (undo) restores what was stored."""
    pid, cid = _h9(client, H4)
    st = _ok(_add(client, pid, cid), 201)
    box_id = st['processors'][-1]['slots'][0]['card']['cvts'][0]['id']
    card = _res_card(client, cid)
    assert (card['cvts'][0]['portCount'], card['trunksUsed']) == (16, 2)
    before = client.get('/api/project').get_json()

    _ok(_set_inputs(client, pid, box_id, 1))
    assert _raw_box(client, box_id)['inputs'] == 1
    card = _res_card(client, cid)
    box = card['cvts'][0]
    assert (box['portCount'], box['trunksIn'], _span(box)) == (8, 1, (1, 8))
    assert (card['trunksUsed'], card['trunksFree']) == (1, 3)

    _ok(client.put('/api/project', json=before))       # undo
    assert 'inputs' not in _raw_box(client, box_id)
    assert _res_card(client, cid)['cvts'][0]['portCount'] == 16

    _ok(_set_inputs(client, pid, box_id, 1))
    _ok(_set_inputs(client, pid, box_id, 2))
    assert 'inputs' not in _raw_box(client, box_id), 'the nameplate stores nothing'
    assert _res_card(client, cid)['cvts'][0]['portCount'] == 16
    for bad in (0, 3, True, '1', None, 1.5):
        assert 'runs on 1 or 2 OPT' in _refused(_set_inputs(client, pid, box_id, bad))
        assert _res_card(client, cid)['cvts'][0]['trunksIn'] == 2


def test_one_to_two_is_refused_with_no_trunk_free_and_writes_nothing(client):
    """Four single-input boxes fill a UHD Jr; putting one back on two OPTs
    needs a trunk nobody has. The refusal names the card and its trunks,
    and nothing in the body is written."""
    pid, cid = _unit(client, UHD_JR)
    for _ in range(4):
        _ok(_add(client, pid, cid, inputs=1), 201)
    box_id = _res_card(client, cid)['cvts'][0]['id']
    why = _refused(client.put(f'/api/processors/{pid}/cvts/{box_id}',
                              json={'inputs': 2, 'name': 'SHOULD NOT LAND'}))
    assert why == ('CVT4K-S on 2 OPT takes 2 trunks, and all 4 trunks on '
                   'NovaPro UHD Jr are used. Free a trunk first.'), why
    raw = _raw_box(client, box_id)
    assert raw['inputs'] == 1 and not raw.get('name'), raw
    # free one, and the same edit goes through - the boxes re-lay in order
    last = _res_card(client, cid)['cvts'][-1]['id']
    _ok(client.delete(f'/api/processors/{pid}/cvts/{last}'))
    _ok(_set_inputs(client, pid, box_id, 2))
    card = _res_card(client, cid)
    assert (card['trunksUsed'], card['trunksFree']) == (4, 0)
    assert card['cvts'][0]['portCount'] == 16


def test_the_add_route_checks_the_effective_take(client):
    """Three CVT10s leave one OPT: the CVT4K-S on its nameplate is refused
    as before, and on one input it goes on - 8 sockets, the fourth OPT."""
    pid, cid = _h9(client, H4)
    for _ in range(3):
        _ok(_add(client, pid, cid, 'novastar-cvt10'), 201)
    assert '1 left' in _refused(_add(client, pid, cid))
    assert 'runs on 1 or 2 OPT' in _refused(_add(client, pid, cid, inputs=3))
    _ok(_add(client, pid, cid, inputs=1), 201)
    card = _res_card(client, cid)
    box = card['cvts'][-1]
    assert (box['deviceId'], box['trunkIndex'], box['portCount']) == (CVT4K, 3, 8)
    assert _span(box) == (25, 32)
    assert card['trunksFree'] == 0


# ── fiber links ──────────────────────────────────────────────────────────

def test_fiber_link_keys_follow_the_inputs(client):
    """One input: one primary link, OPT 1, and one backup input, OPT 3,
    where a backup processor feeds it. Switching 2 to 1 drops the OPT 2 and
    OPT 4 links in the same request, and a cable left with no link goes."""
    pid, cid = _h9(client, H4)
    st = _ok(_add(client, pid, cid), 201)
    box_id = st['processors'][-1]['slots'][0]['card']['cvts'][0]['id']
    _ok(client.put(f'/api/processors/{pid}', json={'backupUnit': {}}))
    box = _res_card(client, cid)['cvts'][0]
    assert box['fiberLinkKeys'] == ['p1', 'p2', 'b1', 'b2']
    tac = _ok(client.post('/api/fiber-cables', json={
        'kind': 'tac', 'strands': 12, 'link': {'boxId': box_id, 'key': 'p1'}}),
        201)['fiberCables'][-1]
    for key in ('p2', 'b1'):
        _ok(client.put(f'/api/processors/{pid}/cvts/{box_id}/fiber-links/{key}',
                       json={'cable': tac['id']}))
    lone = _ok(client.post('/api/fiber-cables', json={
        'kind': 'tac', 'strands': 2, 'link': {'boxId': box_id, 'key': 'b2'}}),
        201)['fiberCables'][-1]
    assert set(_raw_box(client, box_id)['fiberLinks']) == {'p1', 'p2', 'b1', 'b2'}

    st = _ok(_set_inputs(client, pid, box_id, 1))
    box = _res_card(client, cid)['cvts'][0]
    assert box['fiberLinkKeys'] == ['p1', 'b1']
    assert [box['linkTitles'][k] for k in box['fiberLinkKeys']] == ['OPT 1', 'OPT 3']
    assert set(_raw_box(client, box_id)['fiberLinks']) == {'p1', 'b1'}
    cables = [c['id'] for c in st['fiberCables']]
    assert tac['id'] in cables and lone['id'] not in cables, cables
    # and without a backup unit, OPT 1 alone
    _ok(client.put(f'/api/processors/{pid}', json={'backupUnit': None}))
    assert _res_card(client, cid)['cvts'][0]['fiberLinkKeys'] == ['p1']


def test_a_paired_add_brings_its_backup_on_the_same_inputs(client):
    """NovaStar's default pair on a copy/backup H_4xfiber: a single-input
    primary brings a single-input backup, on the trunk that copies it."""
    pid, cid = _h9(client, H4)
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}',
                   json={'mode': 'copy-backup'}))
    raw_card = next(s['card'] for p in _state(client)['processors']
                    for s in p['slots'] if (s.get('card') or {}).get('id') == cid)
    assert catalog.default_backup_pair(raw_card), 'copy/backup makes a pair'
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': CVT4K, 'inputs': 1}), 201)
    raw = st['processors'][-1]['slots'][0]['card']['cvts']
    assert [b.get('inputs') for b in raw] == [1, 1], raw
    card = _res_card(client, cid)
    assert [b['portCount'] for b in card['cvts']] == [8, 8]
    assert card['cvts'][1]['duplicateOf'] == card['cvts'][0]['id']


# ── the browser: + Box, the gear picker and the gear switch ──────────────

SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits; delete proj.snakes;
    await j('PUT', '/api/project', proj);
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-novapro-uhd-jr',
                                                 name: 'JR'});
    const jr = st.processors[0];
    const card = jr.slots[0].card.id;
    for (let n = 0; n < 3; n++) {
        await j('POST', `/api/processors/${jr.id}/cards/${card}/cvts`,
                {deviceId: 'novastar-cvt10', pair: false});
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    await app.refreshProcessors();
    app.renderHardwareDock();
    app.resetHistory('One OPT Seed');
    return {jr: jr.id, card};
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

CARD_JS = """(cardId) => window.app._dockFindCard(cardId).card"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
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


def test_the_box_fits_offer_a_cvt4k_s_on_the_one_trunk_left(page):
    """_cardBoxFits with one trunk free: the CVT4K-S is offered as
    "CVT4K-S (1 OPT)" carrying inputs 1 - in "+ Box", in the dashed slot's
    list and in the gear's picker - and a pick adds it on one OPT."""
    pg, ids = page
    fits = pg.evaluate("""(cardId) => window.app
        ._cardBoxFits(window.app._dockFindCard(cardId).card)
        .map(d => [d.id, d.name, d.addInputs || null, d.pickKey || null])""",
                       ids['card'])
    assert ['novastar-cvt4k-s', 'CVT4K-S (1 OPT)', 1, 'novastar-cvt4k-s:1'] in fits, fits
    assert ['novastar-cvt10', 'CVT10', None, None] in fits, fits
    # the gear's picker lists it under its own key
    assert pg.evaluate(OPEN_GEAR_JS, f"card-{ids['card']}")
    pg.wait_for_timeout(200)
    opts = pg.evaluate("""(cardId) => [...document.querySelectorAll(
        `#hw-gear-popover [data-lrd-field="processor-cvt-add-${cardId}"] option`)]
        .map(o => [o.value, o.textContent])""", ids['card'])
    assert ['novastar-cvt4k-s:1', 'CVT4K-S (1 OPT)'] in opts, opts
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(150)
    # "+ Box": the item adds it on one input, one history entry
    start = pg.evaluate('() => window.app.historyIndex')
    pg.locator(f'[data-lrd-field="dock-addbox-{ids["card"]}"]').click()
    pg.wait_for_timeout(300)
    item = pg.locator(f'[data-lrd-field="dock-addbox-{ids["card"]}-novastar-cvt4k-s:1"]')
    assert item.text_content() == 'CVT4K-S (1 OPT)'
    item.click()
    pg.wait_for_timeout(900)
    card = pg.evaluate(CARD_JS, ids['card'])
    last = card['cvts'][-1]
    assert (last['deviceId'], last['trunksIn'], last['portCount']) == \
        ('novastar-cvt4k-s', 1, 8), last
    assert card['trunksFree'] == 0
    assert pg.evaluate('() => window.app.historyIndex') == start + 1
    assert pg.evaluate('() => window.app.history[window.app.historyIndex].action') \
        == 'Add Breakout Box'
    ids['box'] = last['id']
    assert ids['errors'] == []


def test_the_box_gear_switches_inputs_in_one_entry_and_undoes(page):
    """The CVT4K-S's ⚙: INPUTS, 1 OPT · 2 OPT, lit on what is stored. With
    every trunk used, 2 OPT is refused in words and writes no history;
    after a CVT10 goes, 2 OPT is one 'Set Box Inputs' entry and undo puts
    the box back on one OPT. A CVT10's gear has no switch."""
    pg, ids = page
    box = ids.get('box')
    assert box, 'the add test did not leave a box'
    bar = f'#hw-gear-popover [data-lrd-field="processor-cvt-inputs-{box}"]'
    read = """(sel) => [...document.querySelectorAll(sel + ' button')].map(b =>
        [b.textContent, b.getAttribute('aria-checked')])"""
    assert pg.evaluate(OPEN_GEAR_JS, f'box-{box}')
    pg.wait_for_timeout(200)
    assert pg.evaluate(read, bar) == [['1 OPT', 'true'], ['2 OPT', 'false']]
    assert pg.locator('#hw-gear-popover .hw-pop-box-inputs .hw-pop-red-cap') \
        .text_content() == 'INPUTS'
    if SCRATCH:
        os.makedirs(SCRATCH, exist_ok=True)
        pg.locator('#hw-gear-popover').screenshot(
            path=os.path.join(SCRATCH, 'cvt4k-s-gear-inputs.png'))
    # refused with every trunk used: no entry, the switch stays on 1 OPT
    index = pg.evaluate('() => window.app.historyIndex')
    pg.locator(bar + ' [data-level="2"]').click()
    pg.wait_for_timeout(900)
    assert pg.evaluate('() => window.app.historyIndex') == index
    card = pg.evaluate(CARD_JS, ids['card'])
    assert card['cvts'][-1]['trunksIn'] == 1
    # a CVT10 has no switch
    cvt10 = card['cvts'][0]['id']
    assert pg.evaluate(OPEN_GEAR_JS, f'box-{cvt10}')
    pg.wait_for_timeout(200)
    assert pg.locator('#hw-gear-popover .hw-pop-box-inputs').count() == 0
    pg.keyboard.press('Escape')
    # free a trunk, then 2 OPT: one entry
    pg.evaluate("""async ([jr, id]) => {
        await window.app._processorRequest(`/api/processors/${jr}/cvts/${id}`,
                                           'DELETE', undefined, 'Remove Breakout Box');
    }""", [ids['jr'], cvt10])
    pg.wait_for_timeout(600)
    index = pg.evaluate('() => window.app.historyIndex')
    assert pg.evaluate(OPEN_GEAR_JS, f'box-{box}')
    pg.wait_for_timeout(200)
    pg.locator(bar + ' [data-level="2"]').click()
    pg.wait_for_timeout(900)
    assert pg.evaluate('() => window.app.historyIndex') == index + 1
    assert pg.evaluate('() => window.app.history[window.app.historyIndex].action') \
        == 'Set Box Inputs'
    card = pg.evaluate(CARD_JS, ids['card'])
    mine = next(c for c in card['cvts'] if c['id'] == box)
    assert (mine['trunksIn'], mine['portCount']) == (2, 16), mine
    assert pg.evaluate(OPEN_GEAR_JS, f'box-{box}')
    pg.wait_for_timeout(200)
    assert pg.evaluate(read, bar) == [['1 OPT', 'false'], ['2 OPT', 'true']]
    pg.keyboard.press('Escape')
    pg.evaluate('() => window.app.undo()')
    pg.wait_for_timeout(900)
    card = pg.evaluate(CARD_JS, ids['card'])
    mine = next(c for c in card['cvts'] if c['id'] == box)
    assert (mine['trunksIn'], mine['portCount']) == (1, 8), mine
    stored = pg.evaluate("""(box) => window.app.project.processors
        .flatMap(p => p.slots).map(s => s.card).filter(Boolean)
        .flatMap(c => c.cvts).find(b => b.id === box)""", box)
    assert stored['inputs'] == 1, stored
    assert ids['errors'] == []
