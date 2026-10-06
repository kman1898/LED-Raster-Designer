"""The binder's FIBER CONNECTIONS table: the rack built from the binder.

Each processor's binder page carries one row per fiber output of the
processor - the output by the name the card's face prints ("trunk A" on an
SX40, "OPT 1" on a NovaStar H card, "QD 1 A" on a QD-S, the SQ200's own
"OUT 1"), the cable on it (its kind in brackets the first time the table
names it), the strands in the order they plug in AT THE PROCESSOR, the same
strands AT THE INPUT, and the box input it lands on. A link's strands are
set on the box's own sheet, so their order there is the order at the box:

  - AT THE INPUT reads them as set; a TAC's duplex pair FLIPS between its
    ends, so 1 Blue · 2 Orange set at the box is 2 Orange · 1 Blue at the
    processor; a BiDi link's one strand is the same at both;
  - an MTP crosses inside the cable (both ends read the order as set, and
    the input says so), an opticalCON is one plug that crosses inside;
  - an output with no box reads "not used", an input with no cable "no
    fiber picked", a copper run its copper and length;
  - the backup unit's page carries its own table for the backup inputs
    (X2, OPT 2, IN 2), under the same output names as the main's.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_fiber_connections.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

H4 = 'novastar-card-h-4xfiber'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _ok(resp, code=200):
    assert resp.status_code == code, resp.get_data(as_text=True)[:300]
    return resp.get_json()


# ── the server names every output ────────────────────────────────────────

def test_a_card_names_every_output_its_face_prints(client):
    """card.trunkTitles: every output of the card in order, by the rule a
    box's trunkTitle uses - and a box on two trunks spans two of them."""
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sx40'}), 201)
    sx = next(p for p in st['resolved'] if p['id'] == st['processors'][-1]['id'])
    card = sx['slots'][0]['card']
    assert card['trunkTitles'] == ['trunk A', 'trunk B', 'trunk C', 'trunk D']
    assert [b['trunkTitle'] for b in card['cvts']] == card['trunkTitles']
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': H4}))
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': 'novastar-cvt4k-s'}), 201)
    card = next(p for p in st['resolved'] if p['id'] == pid)['slots'][0]['card']
    assert card['trunkTitles'] == ['OPT 1', 'OPT 2', 'OPT 3', 'OPT 4']
    assert card['cvts'][0]['trunkTitle'] == 'OPT 1-2'
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sq200'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0',
                        json={'deviceId': 'brompton-card-qd-s'}))
    card = next(p for p in st['resolved'] if p['id'] == pid)['slots'][0]['card']
    assert card['trunkTitles'][:2] == ['QD 1 A', 'QD 1 B'] and len(card['trunkTitles']) == 12


# ── the browser: the rows, the backup's table, the painted page ──────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# USC SR: an SX40 (no loops) with its backup processor USC SR BU. XD D is
# removed, so trunk D is empty. TAC A (12, ST) takes XD A's X1 on 1-2 and
# XD B's X1 on 3-4; an opticalCON DUO feeds XD C's X1. On the backup
# inputs TAC B (12, ST) takes XD A's X2 on 1-2, XD B's X2 runs on Cat6 at
# 150 ft, XD C's X2 has nothing picked.
# NOVA: an H9 with an H_4xfiber - a CVT10 on OPT 1, switched to BiDi, on
# TAC C (no connector, strands by number) strand 1; a CVT4K-S on OPT 2-3
# on MTP A, strands 1-2 and 3-4, strand 2 renamed "Rack A"; OPT 4 empty.
# SQ A: an SQ200 with a QD-S on OUT 1 (OUT 2 empty), TAC D on its IN 1
# (1-2) and on the XD-S on QD 1 A's X1 (3-4).
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 8, rows: 8,
                                                     cabinet_width: 200, cabinet_height: 200});
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'brompton'});
    const last = (st) => st.processors[st.processors.length - 1];
    const cable = (st) => st.fiberCables[st.fiberCables.length - 1];
    // USC SR
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: 'USC SR'});
    const sx = last(st).id;
    const xds = last(st).slots[0].card.cvts.map(b => b.id);
    await j('DELETE', `/api/processors/${sx}/cvts/${xds[3]}`);
    await j('PUT', `/api/processors/${sx}`, {backupUnit: {name: 'USC SR BU'}});
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 500, connector: 'ST',
                                               link: {boxId: xds[0], key: 'p1'}});
    const tacA = cable(st);
    await j('PUT', `/api/processors/${sx}/cvts/${xds[1]}/fiber-links/p1`, {cable: tacA.id});
    st = await j('POST', '/api/fiber-cables', {kind: 'opticalcon-duo', ownerBoxId: xds[2],
                                               link: {boxId: xds[2], key: 'p1'}});
    const duo = cable(st);
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 500, connector: 'ST',
                                               link: {boxId: xds[0], key: 'b1'}});
    const tacB = cable(st);
    await j('PUT', `/api/processors/${sx}/cvts/${xds[1]}/fiber-links/b1`, {copper: 'Cat6', ft: 150});
    // NOVA
    st = await j('POST', '/api/processors', {deviceId: 'novastar-h9', name: 'NOVA'});
    const nova = last(st).id;
    st = await j('PUT', `/api/processors/${nova}/slots/0`, {deviceId: 'novastar-card-h-4xfiber'});
    const novaCard = st.processors.find(p => p.id === nova).slots[0].card.id;
    await j('POST', `/api/processors/${nova}/cards/${novaCard}/cvts`, {deviceId: 'novastar-cvt10'});
    st = await j('POST', `/api/processors/${nova}/cards/${novaCard}/cvts`, {deviceId: 'novastar-cvt4k-s'});
    const [cvt10, cvt4k] = st.processors.find(p => p.id === nova).slots[0].card.cvts.map(b => b.id);
    await j('PUT', `/api/processors/${nova}/cvts/${cvt10}/fiber`, {bidi: true});
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 300,
                                               link: {boxId: cvt10, key: 'p1'}});
    const tacC = cable(st);
    await j('PUT', `/api/fiber-cables/${tacC.id}`, {labels: 'numbers'});
    st = await j('POST', '/api/fiber-cables', {kind: 'mtp', strands: 12, ft: 300,
                                               link: {boxId: cvt4k, key: 'p1'}});
    const mtp = cable(st);
    await j('PUT', `/api/processors/${nova}/cvts/${cvt4k}/fiber-links/p2`, {cable: mtp.id});
    await j('PUT', `/api/fiber-cables/${mtp.id}`, {strandName: {strand: 2, name: 'Rack A'}});
    // SQ A
    st = await j('POST', '/api/processors', {deviceId: 'brompton-sq200', name: 'SQ A'});
    const sq = last(st).id;
    st = await j('PUT', `/api/processors/${sq}/slots/0`, {deviceId: 'brompton-card-qd-s'});
    const qd = st.processors.find(p => p.id === sq).slots[0].card.id;
    st = await j('POST', `/api/processors/${sq}/cards/${qd}/cvts`, {deviceId: 'brompton-xd-s'});
    const xds2 = st.processors.find(p => p.id === sq).slots[0].card.cvts[0].id;
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 300, connector: 'LC duplex'});
    const tacD = cable(st);
    await j('PUT', `/api/processors/${sq}/cards/${qd}/fiber-links/p1`, {cable: tacD.id});
    await j('PUT', `/api/processors/${sq}/cvts/${xds2}/fiber-links/p1`, {cable: tacD.id});
    await j('PUT', `/api/processors/${sq}`, {backupUnit: {name: 'SQ B'}});
    // DUAL: an H9 with two H_4xfiber cards, the first named SR, a CVT10 on
    // each one's OPT 1, nothing picked
    st = await j('POST', '/api/processors', {deviceId: 'novastar-h9', name: 'DUAL'});
    const dual = last(st).id;
    const dualCards = [];
    for (const i of [0, 1]) {
        st = await j('PUT', `/api/processors/${dual}/slots/${i}`, {deviceId: 'novastar-card-h-4xfiber'});
        const c = st.processors.find(p => p.id === dual).slots.find(s => s.index === i).card.id;
        dualCards.push(c);
        await j('POST', `/api/processors/${dual}/cards/${c}/cvts`, {deviceId: 'novastar-cvt10'});
    }
    await j('PUT', `/api/processors/${dual}/cards/${dualCards[0]}`, {name: 'SR'});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('fiber_connections_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Fiber Connections Seed');
    return {sx, xds, nova, cvt10, cvt4k, sq, qd, xds2, dual,
            cables: {tacA, tacB, tacC, tacD, duo, mtp}};
}"""

ROWS_JS = """([pid, backup]) => {
    const app = window.app;
    const proc = app._processorsResolved.find(p => p.id === pid);
    return app._bFiberConnectionRows(proc, backup)
        .map(r => ({cells: r.cells, parts: r.parts || null}));
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
    # the seed's last write lands in the app's resolved tree
    from conftest import settled
    settled(pg, lambda: pg.evaluate(
        "(sq) => !!(window.app._processorsResolved || []).find(p => p.id === sq)", ids['sq']),
        bool, 5000)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _rows(pg, pid, backup=False):
    return pg.evaluate(ROWS_JS, [pid, backup])


def test_an_sx40_lists_each_trunk_flips_the_tac_and_says_not_used(page):
    """trunk A and B share TAC A - its kind and ends said once - each pair
    as set at the box, flipped at the processor; trunk C's opticalCON DUO is one plug that crosses
    inside; trunk D has no box. The strands carry their swatches."""
    pg, ids = page
    duo = ids['cables']['duo']['name']
    rows = _rows(pg, ids['sx'])
    assert [r['cells'] for r in rows] == [
        ['trunk A', 'TAC A (TAC 12 · ST)', '2 Orange · 1 Blue', '1 Blue · 2 Orange', 'Tessera XD A · X1'],
        ['trunk B', 'TAC A', '4 Brown · 3 Green', '3 Green · 4 Brown', 'Tessera XD B · X1'],
        ['trunk C', f'{duo} (opticalCON DUO)', 'one plug', 'one plug, crosses inside', 'Tessera XD C · X1'],
        ['trunk D', 'not used', '', '', ''],
    ], rows
    first = rows[0]['parts']
    assert [p['text'] for p in first['3']] == ['1 Blue', '2 Orange']
    assert [p['swatch'] for p in first['3']] == [{'base': '#1F5FA8', 'tracer': None},
                                                 {'base': '#F28020', 'tracer': None}]
    assert [p['swatch']['base'] for p in first['2']] == ['#F28020', '#1F5FA8']
    assert rows[2]['parts'] is None and rows[3]['parts'] is None
    # no backup input on the main's table
    assert not [r for r in rows if 'X2' in r['cells'][4]], rows
    assert ids['errors'] == []


def test_the_backup_units_table_holds_the_backup_inputs_flipped(page):
    """USC SR BU's table: X2 on every XD under the main's output names -
    TAC B flipped at the box, the copper run in its own words, an input
    with nothing picked, and trunk D not used."""
    pg, ids = page
    rows = _rows(pg, ids['sx'], True)
    assert [r['cells'] for r in rows] == [
        ['trunk A', 'TAC B (TAC 12 · ST)', '2 Orange · 1 Blue', '1 Blue · 2 Orange', 'Tessera XD A · X2'],
        ['trunk B', "Cat6 150' (Cat6 runs 100 ft max at 10G)", 'copper', 'copper', 'Tessera XD B · X2'],
        ['trunk C', 'no fiber picked', '', '', 'Tessera XD C · X2'],
        ['trunk D', 'not used', '', '', ''],
    ], rows
    # a processor with no backup unit has no backup table
    assert _rows(pg, ids['nova'], True) == []
    out = pg.evaluate("""(sx) => {
        const app = window.app;
        const proc = app._processorsResolved.find(p => p.id === sx);
        const seen = [];
        app._bTableLines = (book, spec) => { seen.push(spec); return []; };
        app._bKvLines = () => [];
        app._bPullLines = () => [];
        try {
            const group = app._bProcessorGroup({list: {hardware: []}}, proc);
            const main = seen.map(s => s.title);
            seen.length = 0;
            app._bBackupUnitGroup({list: {hardware: []}}, proc, group.name);
            return {main, bu: seen.map(s => s.title)};
        } finally {
            delete app._bTableLines;
            delete app._bKvLines;
            delete app._bPullLines;
        }
    }""", ids['sx'])
    main, bu = out['main'], out['bu']
    # after Breakout boxes, before the strand maps; the backup's on its page
    conn = 'Fiber connections · USC SR · Tessera SX40'
    assert main.index(conn) == main.index('Breakout boxes') + 1, main
    assert main[main.index(conn) + 1].startswith('Strand map · '), main
    assert 'Fiber connections · USC SR BU · Tessera SX40 (backup)' in bu, bu
    assert not [t for t in bu if t.startswith('Fiber connections') and 'backup' not in t], bu


def test_a_bidi_box_keeps_its_one_strand_and_an_mtp_is_not_flipped(page):
    """NOVA: the BiDi CVT10's one strand (TAC C reads strands by number) is
    the same at both ends; the CVT4K-S takes OPT 2 and OPT 3 - a row each -
    on MTP A, the box end in the same order, crossing inside, with strand 2
    by the name it was given; OPT 4 is not used."""
    pg, ids = page
    rows = _rows(pg, ids['nova'])
    cells = [r['cells'] for r in rows]
    box = pg.evaluate("(id) => window.app._bBoxTitle(window.app._dockFindCvt(id).cvt)", ids['cvt4k'])
    assert cells == [
        ['OPT 1', 'TAC C (TAC 12)', '1', '1', 'CVT10 A · OPT 1'],
        ['OPT 2', 'MTP A (MTP 12)', '1 Blue · Rack A', '1 Blue · Rack A · crosses inside', f'{box} · OPT 1'],
        ['OPT 3', 'MTP A', '3 Green · 4 Brown', '3 Green · 4 Brown · crosses inside', f'{box} · OPT 2'],
        ['OPT 4', 'not used', '', '', ''],
    ], cells
    # the words "crosses inside" carry no swatch; every strand does
    far = rows[1]['parts']['3']
    assert [bool(p.get('swatch')) for p in far] == [True, True, False], far
    assert ids['errors'] == []


def test_strand_names_come_through_the_one_namer(page):
    """Every strand cell is fiberStrandName's: a renamed strand, a cable in
    numbers, and a cable in sub-units - "Blue unit · 1 Blue" - each named
    exactly as the strand map names it."""
    pg, ids = page
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const proc = app._processorsResolved.find(p => p.id === ids.nova);
        const mtp = app.getFiberCable(ids.cables.mtp.id);
        const keep = mtp.subunits;
        mtp.subunits = true;
        try {
            const rows = app._bFiberConnectionRows(proc);
            return {rows: rows.map(r => r.cells), names: [1, 2, 3, 4].map(n => app.fiberStrandName(n, mtp))};
        } finally {
            mtp.subunits = keep;
        }
    }""", ids)
    names = out['names']
    assert names == ['Blue unit · 1 Blue', 'Rack A', 'Blue unit · 3 Green', 'Blue unit · 4 Brown'], names
    assert out['rows'][1][2] == f'{names[0]} · {names[1]}', out['rows']
    assert out['rows'][2][3] == f'{names[2]} · {names[3]} · crosses inside', out['rows']
    assert out['rows'][0][2:4] == ['1', '1'], out['rows']


def test_an_sq200_lists_its_outs_and_the_qd_s_outputs(page):
    """SQ A: OUT 1 feeds the QD-S's IN 1, the XD-S on QD 1 A takes TAC D on
    its X1, the QD-S's other eleven outputs are not used, and so is OUT 2.
    Its backup SQ200's table is OUT 1 onto the QD-S's IN 2, and OUT 2."""
    pg, ids = page
    cells = [r['cells'] for r in _rows(pg, ids['sq'])]
    assert cells[0] == ['OUT 1', 'TAC D (TAC 12 · LC duplex)', '2 Orange · 1 Blue', '1 Blue · 2 Orange',
                        'QD 1 · IN 1'], cells
    assert cells[1] == ['QD 1 A', 'TAC D', '4 Brown · 3 Green', '3 Green · 4 Brown', 'QD 1 A · X1'], cells
    assert cells[2:13] == [[f'QD 1 {chr(ord("B") + i)}', 'not used', '', '', ''] for i in range(11)], cells
    assert cells[13:] == [['OUT 2', 'not used', '', '', '']], cells
    # its backup SQ200 feeds the QD-S's IN 2 and nothing behind it
    assert [r['cells'] for r in _rows(pg, ids['sq'], True)] == [
        ['OUT 1', 'no fiber picked', '', '', 'QD 1 · IN 2'],
        ['OUT 2', 'not used', '', '', '']]


def test_each_card_of_a_chassis_names_its_own_outputs(page):
    """DUAL: two cards, each with its own OPT 1 - the output is named with
    its card as the Breakout boxes table names it (SR, else its slot), and
    an input with no cable says so."""
    pg, ids = page
    cells = [r['cells'] for r in _rows(pg, ids['dual'])]
    assert cells == [
        ['SR · OPT 1', 'no fiber picked', '', '', 'CVT10 A · OPT 1'],
        ['SR · OPT 2', 'not used', '', '', ''],
        ['SR · OPT 3', 'not used', '', '', ''],
        ['SR · OPT 4', 'not used', '', '', ''],
        ['slot 2 · OPT 1', 'no fiber picked', '', '', 'CVT10 A · OPT 1'],
        ['slot 2 · OPT 2', 'not used', '', '', ''],
        ['slot 2 · OPT 3', 'not used', '', '', ''],
        ['slot 2 · OPT 4', 'not used', '', '', ''],
    ], cells


def test_a_processor_with_no_boxes_has_no_table(page):
    pg, _ids = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const proc = {id: 'x', name: 'BARE', deviceName: 'H9', slots: [
            {index: 0, name: '', card: {id: 'c', cvts: [], trunkTitles: ['OPT 1', 'OPT 2']}}]};
        return [app._bFiberConnectionRows(proc), app._bFiberConnections(proc, 'BARE')];
    }""")
    assert out == [[], None]


FIT_JS = """() => {
    const app = window.app;
    const opts = { sheet: 'tabloid', palette: 'colour', sides: {power: false, data: true},
                   scope: {kind: 'show'}, cover: false, pull: true, hardware: true, titleBlock: true };
    const plan = app.planBinder(opts);
    const out = [];
    plan.forEach((p, i) => {
        if (!p.title.startsWith('Processors')) return;
        out.push({title: p.title, texts: app.renderBinderPage(opts, i).textInfo});
    });
    return out;
}"""


def test_the_painted_table_is_titled_headed_and_never_cut(page):
    """On the tabloid binder: the table's title in the heading's caps, its
    five headings, and every cell of every table - the main's and the
    backup unit's - painted whole at the cell's own size, wrapped where it
    must be (a list cell is logged as the one text it drew), never cut to
    an ellipsis."""
    pg, ids = page
    pages = pg.evaluate(FIT_JS)
    assert pages, 'no processor pages'
    texts = [t for p in pages for t in p['texts']]
    size = {}
    for t in texts:
        size.setdefault(t['text'], t['size'])
    titles = ('FIBER CONNECTIONS · USC SR · TESSERA SX40',
              'FIBER CONNECTIONS · USC SR BU · TESSERA SX40 (BACKUP)',
              'FIBER CONNECTIONS · NOVA · H9', 'FIBER CONNECTIONS · SQ A · TESSERA SQ200')
    for title in titles:
        assert size.get(title) == 25, (title, sorted(t for t in size if 'FIBER' in t))
    heads = ('OUTPUT', 'CABLE', 'AT THE PROCESSOR', 'AT THE INPUT', 'INPUT')
    for head in heads:
        assert size.get(head) == 21, (head, size.get(head))
    cells = set()
    for pid, backup in ((ids['sx'], False), (ids['sx'], True), (ids['nova'], False), (ids['sq'], False)):
        for row in _rows(pg, pid, backup):
            cells.update(c for c in row['cells'] if c)
    assert "Cat6 150' (Cat6 runs 100 ft max at 10G)" in cells and '1 Blue · Rack A · crosses inside' in cells
    for cell in sorted(cells):
        assert size.get(cell) == 24, (cell, size.get(cell))
    # nothing of the table is cut anywhere it is painted
    ours = set(titles) | set(heads) | cells
    cut = [t['text'] for t in texts if t['text'].endswith('…')
           and any(o.startswith(t['text'][:-1]) for o in ours)]
    assert not cut, cut
    assert ids['errors'] == []


def test_the_input_reads_the_strands_as_set_on_the_box(page):
    """The strands are picked on the box's own sheet, so the order they were
    set in is the order at the box: set 4 Brown · 3 Green on XD B's X1 and
    that is what AT THE INPUT reads, flipped to 3 Green · 4 Brown AT THE
    PROCESSOR. (Last in the module: it puts the link back as it was.)"""
    pg, ids = page
    sx, xd_b = ids['sx'], ids['xds'][1]
    tac = ids['cables']['tacA']['id']
    set_js = """async ([sx, box, cable, strands]) => {
        const r = await fetch(`/api/processors/${sx}/cvts/${box}/fiber-links/p1`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({cable, strands})});
        await window.app.refreshProcessors();
        return r.status;
    }"""
    try:
        assert pg.evaluate(set_js, [sx, xd_b, tac, [4, 3]]) == 200
        row = [r['cells'] for r in _rows(pg, sx) if r['cells'][0] == 'trunk B'][0]
        assert row[2:4] == ['3 Green · 4 Brown', '4 Brown · 3 Green'], row
    finally:
        pg.evaluate(set_js, [sx, xd_b, tac, [3, 4]])
    assert ids['errors'] == []
