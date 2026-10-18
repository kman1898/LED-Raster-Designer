"""A breakout box's inputs on the binder, and "processor" where there is
no card (2026-10-17).

1. The processor page's Breakout boxes table: "the ports should be X1 and
   X2 not 10 in this case. and Opt 1 etc for novastar and it needs to be
   however helios labels them in their documentation" - and then "in this
   example we've put X1 twice and I don't know that's needed". There is
   no PORTS column: FIBER names every input the box takes as a group, in
   its maker's own naming - "X1" over its cable beside its strands, or
   "X1 no fiber" - so the inputs never disappear. The names are the catalog's
   linkPorts (one source: the dock's Fiber section and FIBER CONNECTIONS
   read the same), spelled as each maker's documents spell them - the
   CVT4K-S "OPT1"-"OPT4", the CVT10 "OPT 1" / "OPT 2" as its panel prints
   them. A box switched to one input lists that one. A box whose maker
   names no input (the RS12, the CVT8-5G) keeps the count alone.

2. Only the H series, the MX2000 and the MX6000 hold cards. Every other
   processor - an SX40, a HELIOS, an MX40 Pro - is one unit, and nothing
   shown calls it a card: the processor page's CARDS table is PROCESSOR
   (DEVICE, PORTS, BACKUP - no SLOT, no CARD), and the Breakout boxes
   table's CARD column is PROCESSOR, the cell the processor's name. A
   card-based processor keeps CARDS and CARD exactly as before.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_box_inputs_processor_word.py -v --browser chromium
"""

import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402
import port_assignment  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the catalog: one source for the names and for "card based" ───────────

def test_each_box_names_its_inputs_as_its_maker_does():
    """XD: X1 / X2 (owner, 2026-09-25). CVT4K-S: OPT1-OPT4, no space, as
    NovaStar's specification writes them throughout. CVT10 and CVT10 Pro:
    OPT 1 / OPT 2, as their panels print them. The CVT8-5G's sheet
    contradicts itself and the HELIOS switches' inputs are not named in
    Megapixel's documents, so those keep no names (a neutral Link 1)."""
    def ports(i):
        return (catalog.get_device(i) or {}).get('linkPorts')
    for xd in ('brompton-xd', 'brompton-xd-s', 'brompton-xd-t'):
        assert ports(xd) == {'primary': ['X1'], 'backup': ['X2']}, xd
    assert ports('novastar-cvt4k-s') == {'primary': ['OPT1', 'OPT2'], 'backup': ['OPT3', 'OPT4']}
    for cvt10 in ('novastar-cvt10', 'novastar-cvt10-pro'):
        assert ports(cvt10) == {'primary': ['OPT 1'], 'backup': ['OPT 2']}, cvt10
        assert catalog.get_device(cvt10)['linkPortsSource'].startswith('https://oss.novastar.tech/')
    assert catalog.get_device('novastar-cvt4k-s')['linkPortsSource'].startswith('https://oss.novastar.tech/')
    for undocumented in ('novastar-cvt8-5g', 'megapixel-rs12', 'megapixel-gsm4210p'):
        dev = catalog.get_device(undocumented)
        assert not catalog.link_ports_documented(dev), undocumented
        assert catalog.fiber_link_title('p1', dev) == 'Link 1'
    # the input switch's word still reads OPT off the unspaced spelling
    assert catalog.box_input_word(catalog.get_device('novastar-cvt4k-s')) == 'OPT'
    assert catalog.box_input_word(catalog.get_device('brompton-xd')) == 'input'


def test_only_the_h_series_mx2000_and_mx6000_are_card_based():
    based = sorted(d['id'] for d in catalog.devices('processor') if catalog.is_card_based(d))
    assert based == sorted(['novastar-h2', 'novastar-h5', 'novastar-h9', 'novastar-h9-enhanced',
                            'novastar-h15', 'novastar-h15-enhanced', 'novastar-h20',
                            'novastar-mx2000-pro', 'novastar-mx6000-pro']), based
    # the SQ200 is a chassis, but its OUTs hold QD-S units, never cards
    assert catalog.is_chassis(catalog.get_device('brompton-sq200'))
    assert catalog.unit_word(catalog.get_device('brompton-sq200'),
                             catalog.get_device('brompton-card-qd-s')) == 'QD'
    for proc in ('brompton-sx40', 'megapixel-helios-8k', 'novastar-mx40-pro'):
        assert catalog.unit_word(catalog.get_device(proc)) == 'processor', proc
    assert catalog.unit_word(catalog.get_device('novastar-h9')) == 'card'


def test_messages_say_processor_on_a_one_box_unit_and_card_on_an_h9(client):
    """port_assignment's messages: a move with no free run says "No
    processor has ..." in a show of SX40s, "No card has ..." in a show of
    H9 cards - as it always read there."""
    def unit_words(device):
        client.post('/api/processors', json={'deviceId': device})
        procs = client.get('/api/project').get_json().get('processors') or []
        cards = port_assignment.cards_in(procs)
        return {port_assignment._unit_word(c) for c in cards}, port_assignment._show_unit_word(cards)
    assert unit_words('novastar-mx40-pro') == ({'processor'}, 'processor')
    pid = client.post('/api/processors', json={'deviceId': 'novastar-h9'}).get_json()['processors'][-1]['id']
    client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': 'novastar-card-h-20xrj45'})
    procs = client.get('/api/project').get_json()['processors']
    cards = port_assignment.cards_in(procs)
    assert port_assignment._show_unit_word(cards) == 'card or processor'
    assert port_assignment._show_unit_word([c for c in cards if c['unitWord'] == 'card']) == 'card'


def test_a_resolved_box_says_whether_its_input_names_are_documented(client):
    st = client.post('/api/processors', json={'deviceId': 'megapixel-helios-8k'}).get_json()
    proc = st['processors'][-1]
    cid = proc['slots'][0]['card']['id']
    client.post(f'/api/processors/{proc["id"]}/cards/{cid}/cvts', json={'deviceId': 'megapixel-rs12'})
    res = next(p for p in client.get('/api/processors').get_json()['resolved'] if p['id'] == proc['id'])
    assert res['cardBased'] is False
    box = res['slots'][0]['card']['cvts'][0]
    assert box['linkPortsDocumented'] is False
    st = client.post('/api/processors', json={'deviceId': 'brompton-sx40'}).get_json()
    res = next(p for p in client.get('/api/processors').get_json()['resolved']
               if p['id'] == st['processors'][-1]['id'])
    assert res['slots'][0]['card']['cvts'][0]['linkPortsDocumented'] is True


# ── the binder ───────────────────────────────────────────────────────────

# One processor at a time, in a cleared project. `kind` picks the rig:
#   sx40  - an SX40 "WALL" with its backup unit, XDs on trunks A and B;
#   h9    - an H9 "H9", slot 1 an H_16xRJ45+2xfiber named "SR" carrying a
#           CVT4K-S, slot 2 an H_4xfiber carrying a CVT10;
#   jr    - a NovaPro UHD Jr "JR" with a CVT4K-S switched to one OPT;
#   helios - a HELIOS Standard 8K "HX" with an RS12;
#   mx40  - an MX40 Pro "MX", nothing on it.
SEED_JS = """async (kind) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits; delete proj.snakes; delete proj.binder;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'WALL', columns: 4, rows: 2,
                                       cabinet_width: 200, cabinet_height: 200});
    const add = (deviceId, name) => j('POST', '/api/processors', {deviceId, name})
        .then(st => st.processors[st.processors.length - 1]);
    if (kind === 'sx40') {
        const p = await add('brompton-sx40', 'WALL');
        await j('PUT', `/api/processors/${p.id}`, {backupUnit: {name: 'WALL BU'}});
    } else if (kind === 'h9') {
        const p = await add('novastar-h9', 'H9');
        let st = await j('PUT', `/api/processors/${p.id}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
        let card = st.processors.find(x => x.id === p.id).slots[0].card;
        await j('PUT', `/api/processors/${p.id}/cards/${card.id}`, {name: 'SR'});
        await j('POST', `/api/processors/${p.id}/cards/${card.id}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
        st = await j('PUT', `/api/processors/${p.id}/slots/1`, {deviceId: 'novastar-card-h-4xfiber'});
        card = st.processors.find(x => x.id === p.id).slots[1].card;
        await j('POST', `/api/processors/${p.id}/cards/${card.id}/cvts`, {deviceId: 'novastar-cvt10', pair: false});
    } else if (kind === 'jr') {
        const p = await add('novastar-novapro-uhd-jr', 'JR');
        const card = p.slots[0].card;
        const st = await j('POST', `/api/processors/${p.id}/cards/${card.id}/cvts`,
                           {deviceId: 'novastar-cvt4k-s', pair: false});
        const box = st.processors.find(x => x.id === p.id).slots[0].card.cvts[0];
        await j('PUT', `/api/processors/${p.id}/cvts/${box.id}`, {inputs: 1});
    } else if (kind === 'helios') {
        const p = await add('megapixel-helios-8k', 'HX');
        await j('POST', `/api/processors/${p.id}/cards/${p.slots[0].card.id}/cvts`, {deviceId: 'megapixel-rs12'});
    } else if (kind === 'mx40') {
        await add('novastar-mx40-pro', 'MX');
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('box_inputs_seed');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    const opts = { sheet: 'tabloid', palette: 'colour', sides: {power: true, data: true},
                   scope: {kind: 'show'}, cover: false, pull: false, hardware: true, wiring: false };
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.kind === 'processor');
    if (i < 0) return null;
    const r = app.renderBinderPage(opts, i);
    const proc = app._processorsResolved[0];
    const card = proc.slots.map(s => s.card).find(Boolean);
    return { texts: r.record.ops.filter(o => o.op === 'text').map(o => o.text),
             word: app.unitWordFor(proc, card), show: app.showUnitWord() };
}"""


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
    yield pg, errors
    context.close()


def _sheet(page, kind):
    pg, errors = page
    out = pg.evaluate(SEED_JS, kind)
    assert out, f'no processor sheet for {kind}'
    assert errors == []
    return out


def _run(words, run):
    for i in range(len(words) - len(run) + 1):
        if words[i:i + len(run)] == run:
            return i
    return -1


def _processor_table(words):
    """PROCESSOR, DEVICE, PORTS, BACKUP and no CARDS / SLOT / CARD (PORTS
    here is the processor's socket count, n / N)."""
    at = _run(words, ['PROCESSOR', 'DEVICE', 'PORTS', 'BACKUP'])
    assert at >= 0, words[:40]
    assert 'CARDS' not in words and 'SLOT' not in words and 'CARD' not in words, words[:60]
    return at


def test_brompton_xd_lists_x1_and_x2_under_processor(page):
    """An SX40 with its backup unit: each XD takes X1 from the SX40 and X2
    from the backup - FIBER reads "X1 no fiber" and "X2 no fiber", a
    group each, and no PORTS column. The SX40 has no card: its
    table is PROCESSOR, and the Breakout boxes column reads PROCESSOR with
    the processor's name, WALL, in it."""
    out = _sheet(page, 'sx40')
    words = out['texts']
    assert out['word'] == 'processor' and out['show'] == 'processor'
    at = _processor_table(words)
    assert words[at + 4:at + 6] == ['SX40', '0 / 20'] or words[at + 4] == 'SX40', words[at:at + 8]
    heads = _run(words, ['BREAKOUT BOX', 'PROCESSOR', 'TRUNK', 'FIBER'])
    assert heads >= 0, words
    row = words[heads + 4:heads + 12]
    assert row[:5] == ['XD A', 'WALL', 'trunk A', 'X1 no fiber', 'X2 no fiber'], row
    assert 'PORTS' not in words[heads:heads + 4]
    # the backup unit's own column: PROCESSOR, no slot
    bu = words.index('WALL BU · BACKUP OF WALL') if 'WALL BU · BACKUP OF WALL' in words else None
    tail = words[bu:] if bu is not None else words
    assert _run(tail, ['PROCESSOR', 'DEVICE', 'PORTS', 'BACKS UP']) >= 0, tail[:20]


def test_novastar_boxes_list_opt_inputs_under_card_on_an_h9(page):
    """An H9 keeps CARDS (SLOT, CARD, DEVICE, PORTS, BACKUP) and the
    Breakout boxes column CARD, as before. Its CVT4K-S's FIBER groups read
    "OPT1" and "OPT2" - NovaStar's spelling for that box - and its CVT10
    "OPT 1", as the CVT10's panel prints it; the card's own trunk stays
    "OPT 1-2" / "OPT 1", as NovaStar prints the card's face."""
    out = _sheet(page, 'h9')
    words = out['texts']
    assert out['word'] == 'card' and out['show'] == 'card'
    assert _run(words, ['CARDS', 'SLOT', 'CARD', 'DEVICE', 'PORTS', 'BACKUP']) >= 0, words[:40]
    heads = _run(words, ['BREAKOUT BOX', 'CARD', 'TRUNK', 'FIBER'])
    assert heads >= 0, words
    rows = words[heads + 4:]
    i = rows.index('OPT1 no fiber')
    assert rows[i - 3:i + 2] == [rows[i - 3], 'SR', 'OPT 1-2', 'OPT1 no fiber', 'OPT2 no fiber'], rows[i - 3:i + 2]
    assert rows[i - 3].startswith('CVT4K-S'), rows[i - 3]
    # CVT10 A, its card (slot 2), the card's trunk OPT 1, then the box's
    # own input OPT 1 over its count
    j = next(k for k, w in enumerate(rows) if w.startswith('CVT10'))
    assert rows[j + 1:j + 4] == ['slot 2', 'OPT 1', 'OPT 1 no fiber'], rows[j:j + 5]
    assert 'PROCESSOR' not in words


def test_a_single_input_box_lists_only_the_input_it_uses(page):
    """A CVT4K-S switched to one OPT on a UHD Jr takes OPT1 alone - its
    FIBER is the one group, "OPT1 no fiber" - and the UHD Jr, one unit,
    reads PROCESSOR."""
    words = _sheet(page, 'jr')['texts']
    _processor_table(words)
    heads = _run(words, ['BREAKOUT BOX', 'PROCESSOR', 'TRUNK', 'FIBER'])
    assert heads >= 0, words
    row = words[heads + 4:heads + 9]
    assert row[1:4] == ['JR', row[2], 'OPT1 no fiber'], row
    assert 'OPT2' not in ' '.join(words[heads:heads + 12]), words[heads:heads + 12]


def test_a_helios_reads_processor_and_its_rs12_keeps_the_count(page):
    """Megapixel's documents name no input on the RS12, so its FIBER reads
    as before ("no fiber") and no input name is made up; the HELIOS is one
    unit - PROCESSOR."""
    out = _sheet(page, 'helios')
    words = out['texts']
    assert out['word'] == 'processor'
    _processor_table(words)
    heads = _run(words, ['BREAKOUT BOX', 'PROCESSOR', 'TRUNK', 'FIBER'])
    assert heads >= 0, words
    row = words[heads + 4:heads + 9]
    assert row[1] == 'HX' and row[3] == 'no fiber', row
    assert 'Link 1' not in words, words


def test_an_mx40_pro_reads_processor(page):
    out = _sheet(page, 'mx40')
    assert out['word'] == 'processor'
    at = _processor_table(out['texts'])
    assert out['texts'][at + 4] == 'MX40 Pro', out['texts'][at:at + 8]


# ── the dock says the same ───────────────────────────────────────────────

DOCK_JS = """(kind) => {
    const app = window.app;
    const proc = app._processorsResolved[0];
    const card = proc.slots.map(s => s.card).find(Boolean);
    const gear = document.querySelector(`[data-hwpop="card-${card.id}"]`);
    return { gear: gear ? (gear.title || gear.getAttribute('data-tooltip') || '') : null,
             add: (document.querySelector(`[data-lrd-field="dock-addbox-${card.id}"]`) || {}).title || null };
}"""


@pytest.mark.parametrize('kind,word', [('sx40', 'processor'), ('helios', 'processor'),
                                       ('mx40', 'processor'), ('h9', 'card')])
def test_the_dock_calls_the_unit_what_the_binder_does(page, kind, word):
    pg, _ = page
    _sheet(page, kind)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(600)
    got = pg.evaluate(DOCK_JS, kind)
    assert got['gear'] is not None, got
    assert got['gear'].startswith(f'Configure this {word} '), got
    if got['add'] is not None:
        assert got['add'] == f'Add a breakout box to this {word}.', got


# ── the fiber on the binder: groups, the wiring sheet, the strand map ───

# WALL: an SX40 running both loops with its backup unit, TAC A (24) on XD
# A's X1 (1-2) and X2 (3-4) and XD B's X1 (5-6); ten ports of the wall
# placed. H9: an H_16xRJ45+2xfiber carrying a CVT4K-S on TAC B, OPT1 on
# 1-2 and OPT2 on 3-4. JR: a UHD Jr with a CVT4K-S switched to one OPT on
# TAC C 1-2.
FIBER_SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits; delete proj.snakes; delete proj.binder;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 12, rows: 4,
                                                     cabinet_width: 200, cabinet_height: 200});
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'brompton'});
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: 'WALL'});
    const sx = st.processors[0];
    const xds = sx.slots[0].card.cvts.map(b => b.id);
    await j('PUT', `/api/processors/${sx.id}`, {redundancy: true, backupUnit: {name: 'WALL BU'}});
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 24, ft: 300, connector: 'LC duplex',
                                               link: {boxId: xds[0], key: 'p1'}});
    const tacA = st.fiberCables[st.fiberCables.length - 1].id;
    await j('PUT', `/api/processors/${sx.id}/cvts/${xds[0]}/fiber-links/b1`, {cable: tacA});
    await j('PUT', `/api/processors/${sx.id}/cvts/${xds[1]}/fiber-links/p1`, {cable: tacA, strands: [5, 6]});
    st = await j('POST', '/api/processors', {deviceId: 'novastar-h9', name: 'H9'});
    const h9 = st.processors[st.processors.length - 1];
    st = await j('PUT', `/api/processors/${h9.id}/slots/0`, {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    let card = st.processors.find(x => x.id === h9.id).slots[0].card;
    st = await j('POST', `/api/processors/${h9.id}/cards/${card.id}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
    const big = st.processors.find(x => x.id === h9.id).slots[0].card.cvts[0].id;
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 200, connector: 'LC duplex',
                                               link: {boxId: big, key: 'p1'}});
    const tacB = st.fiberCables[st.fiberCables.length - 1].id;
    await j('PUT', `/api/processors/${h9.id}/cvts/${big}/fiber-links/p2`, {cable: tacB});
    st = await j('POST', '/api/processors', {deviceId: 'novastar-novapro-uhd-jr', name: 'JR'});
    const jr = st.processors[st.processors.length - 1];
    st = await j('POST', `/api/processors/${jr.id}/cards/${jr.slots[0].card.id}/cvts`,
                 {deviceId: 'novastar-cvt4k-s', pair: false});
    const one = st.processors.find(x => x.id === jr.id).slots[0].card.cvts[0].id;
    await j('PUT', `/api/processors/${jr.id}/cvts/${one}`, {inputs: 1});
    await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 100, connector: 'LC duplex',
                                          link: {boxId: one, key: 'p1'}});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('box_inputs_fiber_seed');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(wall.id), cardId: sx.slots[0].card.id, lastIndex: 9});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    return {sx: sx.id, h9: h9.id, jr: jr.id, xds, big, one, tacA};
}"""

PAGE_JS = """([kind, title, wiring]) => {
    const app = window.app;
    const opts = { sheet: 'tabloid', palette: 'colour', sides: {power: false, data: true},
                   scope: {kind: 'show'}, cover: false, pull: false, hardware: true, wiring: !!wiring };
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.kind === kind && (!title || p.title.includes(title)));
    if (i < 0) return null;
    const r = app.renderBinderPage(opts, i);
    return { scale: plan[i].scale || 1, title: plan[i].title,
             texts: r.record.ops.filter(o => o.op === 'text'),
             rects: r.record.ops.filter(o => o.op === 'rect'), wiring: r.wiring };
}"""


@pytest.fixture(scope="module")
def fiber(page):
    pg, errors = page
    ids = pg.evaluate(FIBER_SEED_JS)
    pg.wait_for_timeout(600)
    return pg, ids, errors


def _texts(sheet, text):
    return [t for t in sheet['texts'] if t['text'] == text]


def test_fiber_groups_carry_the_input_names_and_the_row_centres_on_them(fiber):
    """The Breakout boxes table, XD A: no PORTS column; FIBER's groups
    name the inputs - "X1" over "TAC A (TAC 24)" beside 1 Blue over 2
    Orange, "X2" beside 3 Green over 4 Brown, each outlined - and the
    row's other cells sit centred on the groups, not at the top. XD B's
    X2 has nothing on it: its group reads "X2 no fiber"."""
    pg, ids, errors = fiber
    sheet = pg.evaluate(PAGE_JS, ['processor', 'WALL', False])
    assert sheet, 'no WALL processor sheet'
    words = [t['text'] for t in sheet['texts']]
    heads = _run(words, ['BREAKOUT BOX', 'PROCESSOR', 'TRUNK', 'FIBER'])
    assert heads >= 0, words[:80]
    blue, orange = _texts(sheet, '1 Blue')[0], _texts(sheet, '2 Orange')[0]
    green, brown = _texts(sheet, '3 Green')[0], _texts(sheet, '4 Brown')[0]
    label = [t for t in _texts(sheet, 'X1') if abs(t['y'] - blue['y']) < 0.6]
    assert label and label[0]['x'] < blue['x'], (label, blue)
    assert [t for t in _texts(sheet, 'X2') if abs(t['y'] - green['y']) < 0.6]
    assert 'X2 no fiber' in words, words
    # the box's name centred down its row: between X1's strands and X2's
    xd = _texts(sheet, 'XD A')[0]
    assert blue['y'] < xd['y'] < brown['y'], (xd, blue, brown)
    outlines = [r for r in sheet['rects'] if str(r.get('stroke') or '').lower() == '#666666'
                and not r.get('fill')]
    assert any(r['y'] < blue['y'] - 18 and orange['y'] < r['y'] + r['h'] < green['y'] - 18
               for r in outlines), 'X1 has no outline of its own'
    assert errors == []


def test_fiber_connections_never_splits_a_box_name(fiber):
    """BREAKOUT reads "X1 on XD A": it breaks only after its " on ", so a
    box's name is never cut in two."""
    pg, ids, errors = fiber
    pieces = pg.evaluate("() => window.app._bCellPieces('X1 on XD S1 A', 'on')")
    assert pieces == ['X1 on ', 'XD S1 A'], pieces
    sheet = pg.evaluate(PAGE_JS, ['processor', 'WALL', False])
    words = [t['text'] for t in sheet['texts']]
    i = words.index('X1 on') if 'X1 on' in words else words.index('X1 on XD A')
    assert words[i] == 'X1 on XD A' or words[i + 1] == 'XD A', words[i:i + 3]


def test_the_strand_map_names_the_box_ports_each_link_carries(fiber):
    """STRAND MAP's BOX PORTS: an XD's X1 and X2 carry its 1-10 (the loop's
    far box XD B too); a CVT4K-S on two inputs carries OPT1 1-8 and OPT2
    9-16, as NovaStar maps them; one switched to one OPT carries 1-8 on it."""
    pg, ids, errors = fiber
    maps = pg.evaluate("""(ids) => {
        const app = window.app;
        const of = (id) => app._bStrandMaps(app._processorsResolved.find(p => p.id === id))
            .map(m => ({ cols: m.cols.map(c => c.title), rows: m.rows.map(r => r.cells) }));
        return { sx: of(ids.sx), h9: of(ids.h9), jr: of(ids.jr) };
    }""", ids)
    sx = maps['sx'][0]
    assert sx['cols'] == ['strand', 'link', 'box ports'], sx
    assert sx['rows'][:6] == [['1 Blue', 'XD A · X1', '1-10'], ['2 Orange', 'XD A · X1', '1-10'],
                              ['3 Green', 'XD A · X2', '1-10'], ['4 Brown', 'XD A · X2', '1-10'],
                              ['5 Slate', 'XD B · X1', '1-10'], ['6 White', 'XD B · X1', '1-10']], sx
    assert sx['rows'][6] == ['7 Red', 'spare', ''], sx
    h9 = maps['h9'][0]['rows']
    assert [r[1:] for r in h9[:4]] == [['CVT4K-S A-B · OPT1', '1-8'], ['CVT4K-S A-B · OPT1', '1-8'],
                                        ['CVT4K-S A-B · OPT2', '9-16'], ['CVT4K-S A-B · OPT2', '9-16']], h9
    jr = maps['jr'][0]['rows']
    assert [r[2] for r in jr[:2]] == ['1-8', '1-8'] and jr[0][1].endswith('· OPT1'), jr
    assert errors == []


def _wiring_consts(*names):
    """The wiring sheet's own constants, read out of app-binder-wiring.js."""
    src = io.open(os.path.join(os.path.dirname(__file__), '..', 'src', 'static', 'js',
                               'app-binder-wiring.js'), encoding='utf-8').read()
    out = []
    for name in names:
        m = re.search(r'\b%s\s*=\s*(-?[0-9.]+)' % name, src)
        assert m, 'app-binder-wiring.js no longer defines ' + name
        out.append(float(m.group(1)))
    return out


BOX_H, IN_LINE, PAD = _wiring_consts('BOX_H', 'IN_LINE', 'PAD')
FIBER_HEXES = {'#f28020', '#1f5fa8', '#1a9a48', '#7a4a2e'}


def _wiring_block(sheet, prefix):
    half = sheet['wiring']['halves'][0]
    block = next(b for b in half['blocks'] if b['title'].startswith(prefix))
    inside = [t for t in sheet['texts'] if block['x'] <= t['x'] <= block['x'] + block['w']
              and block['y'] <= t['y'] <= block['y'] + block['h']]
    return half, block, inside


def _rects_meet(a, b, pad=0.0):
    return (min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x']) > -pad
            and min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y']) > -pad)


def _clear_of_sockets_and_runs(half, block):
    """No input outline touches a socket circle or overlaps another, all
    stay inside the box, and no run passes through one."""
    groups = block['inputs']
    for g in groups:
        assert block['x'] < g['x'] and g['x'] + g['w'] < block['x'] + block['w'], (g, block)
        assert block['y'] < g['y'] and g['y'] + g['h'] < block['y'] + block['h'], (g, block)
        for sk in block['sockets']:
            disc = {'x': sk['x'] - sk['r'], 'y': sk['y'] - sk['r'], 'w': 2 * sk['r'], 'h': 2 * sk['r']}
            assert not _rects_meet(g, disc), ('an input outline on a socket', g, sk)
    for i, a in enumerate(groups):
        for b in groups[i + 1:]:
            assert not _rects_meet(a, b), ('two input outlines overprint', a, b)
    for r in half['runs']:
        for p, q in zip(r['points'], r['points'][1:]):
            seg = {'x': min(p[0], q[0]), 'y': min(p[1], q[1]),
                   'w': abs(p[0] - q[0]), 'h': abs(p[1] - q[1])}
            for g in groups:
                assert not _rects_meet(seg, g), ('a run through an input outline', r['from'], g)


def test_the_data_wiring_inputs_sit_beside_the_caption_on_its_row(fiber):
    """WALL's DATA WIRING sheet (owner, 2026-10-18: "they dont need to be
    stacked. they can be side by side and on the same row as the name of
    the box"): inside XD A's block, after its caption and on the caption's
    own baseline, "X1" with 2 Orange and 1 Blue (box-end order, as FIBER
    CONNECTIONS' AT THE BREAKOUT reads), swatched, then "X2" with 4 Brown
    and 3 Green beside it - each group outlined, at the caption's size,
    clear of every socket and every run. The box is two rows again -
    sockets, then caption and inputs - every box on the sheet one height."""
    pg, ids, errors = fiber
    sheet = pg.evaluate(PAGE_JS, ['wiring', 'WALL', True])
    assert sheet and sheet['wiring'], 'no WALL data wiring sheet'
    half, block, inside = _wiring_block(sheet, 'XD A')
    s = half['scale']
    # WALL's ports start one to a row, all four rows: on the whole no nearer
    # the wall's top than its foot, so the boxes stand under it as they did
    assert [b['side'] for b in half['blocks']] == ['bottom', 'bottom'], half['blocks']
    words = [t['text'] for t in inside]
    cap = next(t for t in inside if t['text'] == block['title'])
    i = words.index('X1')
    assert words[i:i + 6] == ['X1', '2 Orange', '1 Blue', 'X2', '4 Brown', '3 Green'], words
    cap_w = pg.evaluate("""([text, size]) => { const app = window.app, c = app._binderMeasureCtx
        || document.createElement('canvas').getContext('2d');
        c.font = app._bFont(size, 700); return c.measureText(text).width; }""", [cap['text'], cap['size']])
    for t in inside[i:i + 6]:
        # the caption's own row - the same baseline - and to its right
        assert abs(t['y'] - cap['y']) < 0.6, ('an input off the caption row', t, cap)
        assert t['x'] > cap['x'] + cap_w, ('an input over the caption', t, cap, cap_w)
        assert t['size'] >= cap['size'] - 0.01, (t, cap)
    # X1's group, then X2's, left to right
    x1, x2 = inside[i], inside[i + 3]
    assert x1['x'] < inside[i + 2]['x'] < x2['x'], (x1, x2)
    groups = block['inputs']
    assert [g['head'] for g in groups] == ['X1', 'X2'] and all(g['line'] == 0 for g in groups), groups
    for g in groups:
        # the outline is the caption's band: round the baseline, past the
        # caption's right end
        assert g['y'] < cap['y'] - cap['size'] * 0.7 and cap['y'] < g['y'] + g['h'], (g, cap)
        assert g['x'] > cap['x'] + cap_w, (g, cap)
    assert groups[0]['x'] + groups[0]['w'] < groups[1]['x'], groups
    _clear_of_sockets_and_runs(half, block)
    # two rows: the box no taller than a box with no inputs, all alike
    assert {round(b['h'], 2) for b in half['blocks']} == {round(BOX_H * s, 2)}, half['blocks']
    sock = max(sk['y'] + sk['r'] for sk in block['sockets'])
    fills = {str(r.get('fill') or '').lower() for r in sheet['rects']
             if block['x'] <= r['x'] <= block['x'] + block['w'] and sock < r['y'] < block['y'] + block['h']}
    assert {'#f28020', '#1f5fa8'} <= fills, fills
    assert errors == []


def test_a_narrow_box_wraps_its_inputs_under_the_caption(fiber):
    """Where the caption's row cannot hold the caption and every group -
    a long box name, and no room on the sheet's bottom row to widen the
    box - the groups wrap, all of them, to a line under the caption, from
    its left edge, still side by side and outlined; the caption is not
    shrunk; every box on the sheet grows by that one line, alike."""
    pg, ids, errors = fiber
    sx, box = ids['sx'], ids['xds'][0]
    long_name = 'XD A UPSTAGE LEFT TRUSS POSITION FOUR OVER THE DECK'
    put = """async ([sx, box, name]) => {
        await fetch(`/api/processors/${sx}/cvts/${box}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name})});
        await window.app.refreshProcessors();
        await window.app.refreshPortAssignment();
    }"""
    before = pg.evaluate("""([sx, box]) => (window.app.project.processors.find(p => p.id === sx)
        .slots[0].card.cvts.find(b => b.id === box).name) || ''""", [sx, box])
    pg.evaluate(put, [sx, box, long_name])
    try:
        sheet = pg.evaluate(PAGE_JS, ['wiring', 'WALL', True])
        half, block, inside = _wiring_block(sheet, long_name)
        s = half['scale']
        cap = next(t for t in inside if t['text'] == block['title'])
        assert abs(cap['size'] - _texts(sheet, block['title'])[0]['size']) < 0.01
        words = [t['text'] for t in inside]
        i = words.index('X1')
        assert words[i:i + 6] == ['X1', '2 Orange', '1 Blue', 'X2', '4 Brown', '3 Green'], words
        for t in inside[i:i + 6]:
            # one line under the caption
            assert abs(t['y'] - (cap['y'] + IN_LINE * s)) < 0.6, ('not on the line under the caption', t, cap)
            assert t['size'] >= cap['size'] - 0.01, (t, cap)
        groups = block['inputs']
        assert [g['line'] for g in groups] == [1, 1], groups
        # from the caption's left edge, side by side
        assert abs(groups[0]['x'] - (block['x'] + PAD * s)) < 0.6, (groups[0], block)
        assert groups[0]['x'] + groups[0]['w'] < groups[1]['x'], groups
        assert all(g['y'] > cap['y'] for g in groups), (groups, cap)
        _clear_of_sockets_and_runs(half, block)
        # the line is added to every box on the sheet
        assert {round(b['h'], 2) for b in half['blocks']} == {round((BOX_H + IN_LINE) * s, 2)}, half['blocks']
    finally:
        pg.evaluate(put, [sx, box, before])
    assert errors == []


def test_the_data_wiring_inputs_print_numbers_where_the_cable_reads_in_numbers(fiber):
    """A cable labelled by number: the same block reads "X1 2 1", no
    strand swatch."""
    pg, ids, errors = fiber
    pg.evaluate("""async (id) => {
        await fetch(`/api/fiber-cables/${id}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({labels: 'numbers'})});
        await window.app.refreshProcessors();
        await window.app.refreshPortAssignment();
    }""", ids['tacA'])
    try:
        sheet = pg.evaluate(PAGE_JS, ['wiring', 'WALL', True])
        half = sheet['wiring']['halves'][0]
        block = next(b for b in half['blocks'] if b['title'].startswith('XD A'))
        inside = [t for t in sheet['texts'] if block['x'] <= t['x'] <= block['x'] + block['w']
                  and block['y'] <= t['y'] <= block['y'] + block['h']]
        words = [t['text'] for t in inside]
        i = words.index('X1')
        assert words[i:i + 6] == ['X1', '2', '1', 'X2', '4', '3'], words
        sock = max(s['y'] + s['r'] for s in block['sockets'])
        fiber_hexes = {'#f28020', '#1f5fa8', '#1a9a48', '#7a4a2e'}
        assert not [r for r in sheet['rects'] if str(r.get('fill') or '').lower() in fiber_hexes
                    and block['x'] <= r['x'] <= block['x'] + block['w'] and r['y'] > sock]
    finally:
        pg.evaluate("""async (id) => {
            await fetch(`/api/fiber-cables/${id}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({labels: 'colors'})});
            await window.app.refreshProcessors();
        }""", ids['tacA'])
    assert errors == []


def test_a_box_over_the_wall_keeps_its_inputs_on_the_caption_row(fiber):
    """WALL with only its first two ports placed: both start on the wall's
    upper rows, so XD A and XD B stand OVER the wall (2026-10-18, "put the
    breakouts up top"). A box there is the same box turned over - its runs
    come up into its sockets, so the sockets are at its foot and the caption
    at its head - and the inputs stay where they were asked for: side by
    side on the caption's own row, after the caption, outlined and
    swatched, clear of every socket and every run."""
    pg, ids, errors = fiber
    layer = pg.evaluate("() => String(window.app.project.layers[0].id)")
    move = """async ([layer, index, card]) => {
        const app = window.app;
        if (card) await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                               {layerId: layer, cardId: card, lastIndex: 9});
        else await app._assignmentRequest('/api/port-assignments/unpin', 'POST', {layerId: layer, index});
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app.renderLayers();
    }"""
    card = pg.evaluate("(sx) => window.app.project.processors.find(p => p.id === sx).slots[0].card.id", ids['sx'])
    for index in (3, 2):
        pg.evaluate(move, [layer, index, None])
    try:
        sheet = pg.evaluate(PAGE_JS, ['wiring', 'WALL', True])
        half, block, inside = _wiring_block(sheet, 'XD A')
        s = half['scale']
        m = half['map']
        assert [b['side'] for b in half['blocks']] == ['top', 'top'], half['blocks']
        assert block['y'] + block['h'] < m['y'], (block, m)
        cap = next(t for t in inside if t['text'] == block['title'])
        top_of_sockets = min(sk['y'] - sk['r'] for sk in block['sockets'])
        assert cap['y'] < top_of_sockets, ('the caption over the numbers', cap, top_of_sockets)
        words = [t['text'] for t in inside]
        i = words.index('X1')
        assert words[i:i + 6] == ['X1', '2 Orange', '1 Blue', 'X2', '4 Brown', '3 Green'], words
        for t in inside[i:i + 6]:
            assert abs(t['y'] - cap['y']) < 0.6, ('an input off the caption row', t, cap)
            assert t['x'] > cap['x'], (t, cap)
        groups = block['inputs']
        assert [g['head'] for g in groups] == ['X1', 'X2'] and all(g['line'] == 0 for g in groups), groups
        for g in groups:
            assert g['y'] + g['h'] < top_of_sockets, ('an input outline down among the sockets', g)
        _clear_of_sockets_and_runs(half, block)
        assert {round(b['h'], 2) for b in half['blocks']} == {round(BOX_H * s, 2)}, half['blocks']
        fills = {str(r.get('fill') or '').lower() for r in sheet['rects']
                 if block['x'] <= r['x'] <= block['x'] + block['w'] and block['y'] < r['y'] < top_of_sockets}
        assert {'#f28020', '#1f5fa8'} <= fills, fills
        # every run comes UP into its socket, onto the socket's foot
        for r in half['runs']:
            if r['device'] != block['title']:
                continue
            sk = next(x for x in block['sockets'] if x['n'] == r['socket'])
            tail, before = r['points'][-1], r['points'][-2]
            assert abs(tail[0] - sk['x']) < 0.01 and abs(tail[1] - (sk['y'] + sk['r'])) < 0.01, (r, sk)
            assert before[1] > tail[1], ('the run comes up into the socket', r)
    finally:
        pg.evaluate(move, [layer, None, card])
    after = pg.evaluate(PAGE_JS, ['wiring', 'WALL', True])
    assert [b['side'] for b in after['wiring']['halves'][0]['blocks']] == ['bottom', 'bottom']
    assert errors == []
