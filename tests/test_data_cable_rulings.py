"""Data and fiber cables: the owner's rulings of 2026-10-21.

  1. One word for a data home run on every surface - "etherCON" where the
     box's output is etherCON, "Cat6" where it is plain RJ45 or nobody
     documented it (dataCableWord). A snake is "<word> Snake", its
     extension "<word> Extension", a coupler "<word> Barrel".
  2. A box never borrows its card's (or processor's) connector: it answers
     for itself, else Cat6. The card's own front ports keep the card's.
  3. A data home run with no length prints a row: the word, an empty
     length and "no length" in Notes - the pull sheet and the binder's
     CABLES alike.
  4. The SQ200 -> QD-S input fiber goes where the QD-S is (its boxes'
     location), and on the screen's CABLES table.
  5. Every cable-stock join adds a barrel (per channel on a snake); a power
     multi needs none (tests/test_cable_stock.py counts them on the stock).
  6. An extension is a type of its own, so its "ext · <snake>" note never
     rides onto the home runs of the same length. It and its barrel are
     labelled by the socket's own port label; a snake by its ports, its
     name and size in Notes, and two snakes never merge.
  7. A blank cabinet counts nothing on a hand-drawn data path.
  8. A fiber cable with no length is flagged on every surface.
  9. pullGuessSide puts free data rows on the data side.

Run locally (each session takes its own free port):
    python -m pytest tests/test_data_cable_rulings.py -v --browser chromium
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── 2. a box answers for its own connector ───────────────────────────────

def _patch_connectors(monkeypatch, connectors):
    """The catalog with these devices' ``connector`` set (None removes it)."""
    cat = copy.deepcopy(catalog.load_catalog())
    for d in cat['devices']:
        if d['id'] in connectors:
            if connectors[d['id']] is None:
                d.pop('connector', None)
            else:
                d['connector'] = connectors[d['id']]
    monkeypatch.setattr(catalog, 'load_catalog', lambda force=False: cat)


def _h9_card_box(client):
    st = client.post('/api/processors', json={'deviceId': 'novastar-h9'}).get_json()
    pid = st['processors'][-1]['id']
    client.put(f'/api/processors/{pid}/slots/0',
               json={'deviceId': 'novastar-card-h-16xrj45-2xfiber'})
    st = client.get('/api/processors').get_json()
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    r = client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                    json={'deviceId': 'novastar-cvt4k-s', 'pair': False})
    assert r.status_code == 201, r.get_data(as_text=True)
    return pid


def _connectors(client, pid):
    st = client.get('/api/processors').get_json()
    card = next(p for p in st['resolved'] if p['id'] == pid)['slots'][0]['card']
    return card['portConnector'], card['cvts'][0]['portConnector']


def test_a_box_never_borrows_its_cards_connector(client, monkeypatch):
    """A CVT4K-S under a card documented etherCON reads Cat6 (it documents
    nothing itself) while the card's own front ports read etherCON; a box
    documented etherCON under an RJ45 card reads etherCON while the card
    reads Cat6."""
    _patch_connectors(monkeypatch, {'novastar-card-h-16xrj45-2xfiber': 'ethercon',
                                    'novastar-cvt4k-s': None})
    pid = _h9_card_box(client)
    assert _connectors(client, pid) == ('ethercon', 'cat')
    _patch_connectors(monkeypatch, {'novastar-card-h-16xrj45-2xfiber': 'rj45',
                                    'novastar-cvt4k-s': 'ethercon'})
    assert _connectors(client, pid) == ('cat', 'ethercon')


def test_the_catalog_states_each_units_data_outputs():
    """Every unit whose copper outputs the manufacturer's spec sheet names
    carries them: etherCON reads etherCON, plain RJ45 reads Cat6. Fiber
    only, SFP and chassis units carry no copper word; a card keeps its own
    (the H cards' RJ45, the fiber cards' fiber)."""
    dev = {d['id']: d for d in catalog.load_catalog()['devices']}
    word = lambda i: dev[i].get('connector')
    for i in ('novastar-mx40-pro', 'novastar-mx30', 'novastar-mx20', 'novastar-cx40-pro',
              'novastar-cx80-pro', 'novastar-mctrl4k', 'novastar-mctrl660-pro',
              'novastar-mctrl-r5', 'novastar-novapro-uhd', 'novastar-novapro-uhd-jr',
              'novastar-novapro-hd', 'novastar-4k-prime', 'novastar-cvt4k-s',
              'novastar-cvt10-pro', 'brompton-sx40', 'brompton-s8', 'brompton-s4',
              'brompton-m2', 'brompton-t1',
              'brompton-xd', 'brompton-xd-t', 'megapixel-rs12'):
        assert word(i) == 'ethercon', i
    for i in ('novastar-ku20', 'novastar-vx400', 'novastar-vx400-pro', 'novastar-vx600',
              'novastar-vx600-pro', 'novastar-vx1000', 'novastar-vx1000-pro',
              'novastar-vx2000-pro', 'novastar-vx16s', 'novastar-vx6s', 'novastar-vx4s',
              'novastar-mctrl660', 'novastar-mctrl700', 'novastar-mctrl600',
              'novastar-mctrl300', 'novastar-msd300', 'novastar-cvt10', 'novastar-cvt8-5g',
              'brompton-xd-s', 'megapixel-gsm4210p',
              'novastar-card-h-20xrj45', 'novastar-card-h-16xrj45-2xfiber'):
        assert word(i) == 'rj45', i
    for i in ('novastar-h9', 'novastar-mx6000-pro', 'brompton-sq200', 'brompton-card-qd-s'):
        assert word(i) is None, i
    assert word('novastar-card-h-4xfiber') == 'fiber'
    # the words print through the one table
    assert catalog.data_port_connector(None, dev['novastar-mx40-pro'], None) == 'ethercon'
    assert catalog.data_port_connector(dev['brompton-xd-s'], None, None, box=True) == 'cat'
    assert catalog.data_port_connector(dev['brompton-xd'], None, None, box=True) == 'ethercon'


def test_the_server_takes_an_ethercon_pick(client):
    """etherCON is in the connector list, so a port cable or a snake may
    store it; a pick outside the list is still refused."""
    pid = _h9_card_box(client)
    st = client.get('/api/processors').get_json()
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    r = client.put(f'/api/processors/{pid}/cards/{cid}',
                   json={'portCables': {'10': {'ft': 50, 'connector': 'ethercon'}}})
    assert r.status_code == 200, r.get_data(as_text=True)
    st = client.get('/api/processors').get_json()
    card = next(p for p in st['resolved'] if p['id'] == pid)['slots'][0]['card']
    assert card['portCables']['10'] == {'ft': 50, 'connector': 'ethercon'}
    r = client.put(f'/api/processors/{pid}/cards/{cid}',
                   json={'portCables': {'10': {'ft': 50, 'connector': 'usb'}}})
    assert r.status_code == 400


# ── the browser: the pull list's seed ────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_pull_list import SEED_JS, _rows  # noqa: E402

REBUILD_JS = """async () => {
    const app = window.app;
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app._circuitTailCache = null;
    return JSON.parse(JSON.stringify(app.buildPullList()));
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
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    ids['errors'] = errors
    yield pg, ids
    context.close()


HELPERS_JS = """
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const rebuild = async () => {
        await app.refreshProcessors();
        await app.refreshPortAssignment();
        app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(app.buildPullList()));
    };
    const layer = (id) => app.project.layers.find(l => l.id === id);
    const cardUrl = `/api/processors/${ids.procId}/cards/${ids.cardId}`;
    const aSock = String(ids.sockets['WALL-A'][0]);
    const cSock = String(ids.sockets['CENTER'][0]);
    const dataRows = (rows) => rows.filter(r => r.side === 'data' && !/Jump|^H9$/.test(r.type));
    // the binder's CABLES THIS SCREEN cells for one screen
    const cablesCells = (list, l) => {
        const orig = app._bTableLines;
        let spec = null;
        app._bTableLines = (b, s) => { spec = s; return []; };
        try { app._bCableTable({ list }, { kind: 'screen', layers: [l] }, 'data'); }
        finally { app._bTableLines = orig; }
        return spec.rows.map(r => r.cells);
    };
"""


def test_one_word_for_a_data_home_run_on_every_surface(page):
    """Unpicked, every data run reads Cat6 - the pull sheet's rows, the
    run text the map tag, the tray chip and the binder print. An etherCON
    pick reads etherCON everywhere: "etherCON 50'", "etherCON Snake",
    "etherCON Extension" and its "etherCON Barrel"."""
    pg, ids = page
    out = pg.evaluate("""async (ids) => {""" + HELPERS_JS + """
        const before = await rebuild();
        const cText = app.dataPortCable(ids.cardId, cSock).text;
        const snake = app.getShowSnakes()[0];
        await j('PUT', `/api/snakes/${snake.id}`, {connector: 'ethercon'});
        await j('PUT', cardUrl, {portCables: {[cSock]: {ft: 50, connector: 'ethercon'},
                                              [aSock]: {ft: 25}}});
        const picked = await rebuild();
        const res = {
            words: [app.dataCableWord('cat'), app.dataCableWord('ethercon'), app.dataCableWord(null),
                    app.dataCableWord('nonsense')],
            before: before.positions.map(p => dataRows(p.rows)),
            cText,
            picked: picked.positions.map(p => dataRows(p.rows)),
            pickedText: app.dataPortCable(ids.cardId, cSock).text,
            aLabel: app.getPortLabelText(layer(ids.a), 1, 'primary'),
        };
        await j('PUT', `/api/snakes/${snake.id}`, {connector: null});
        await j('PUT', cardUrl, {portCables: {[cSock]: {ft: 50}}});
        await rebuild();
        return res;
    }""", ids)
    assert out['words'] == ['Cat6', 'etherCON', 'Cat6', 'Cat6']
    assert _rows(out['before'][0]) == [('Cat6 Snake', "100'", 1, 'SR-1, SR-2', 'SNAKE A · 2 channel')]
    assert _rows(out['before'][1]) == [('Cat6', "50'", 1, ids['centerPortLabel'], '')]
    assert out['cText'] == "50' Cat6"
    la = out['aLabel']
    # the extension follows the box's own word (the card's RJ45: Cat6); the
    # snake and the loose run take their etherCON picks
    assert _rows(out['picked'][0]) == [
        ('Cat6 Barrel', 'EA', 1, la, ''),
        ('Cat6 Extension', "25'", 1, la, 'ext · SNAKE A'),
        ('etherCON Snake', "100'", 1, 'SR-1, SR-2', 'SNAKE A · 2 channel')], out['picked']
    assert _rows(out['picked'][1]) == [('etherCON', "50'", 1, ids['centerPortLabel'], '')]
    assert out['pickedText'] == "50' etherCON"
    assert ids['errors'] == []


def test_a_home_run_with_no_length_prints_a_row(page):
    """CENTER's socket with no cable typed: one Cat6 row with an empty
    length and "no length" in Notes - in its position, on the processor's
    rows and on the screen's own reading, so the binder's CABLES THIS
    SCREEN lists it ("no length" in LENGTH) rather than dropping it."""
    pg, ids = page
    out = pg.evaluate("""async (ids) => {""" + HELPERS_JS + """
        await j('PUT', cardUrl, {portCables: {}});
        const list = await rebuild();
        const res = {
            center: dataRows(list.positions[1].rows),
            hw: list.hardware.filter(h => h.kind === 'processor').map(h => dataRows(h.rows))[0],
            screen: dataRows(list.byScreen[String(ids.c)].rows),
            cables: cablesCells(list, layer(ids.c)),
        };
        await j('PUT', cardUrl, {portCables: {[cSock]: {ft: 50}}});
        await rebuild();
        return res;
    }""", ids)
    want = ('Cat6', '', 1, ids['centerPortLabel'], 'no length')
    assert _rows(out['center']) == [want], out['center']
    assert want in _rows(out['hw']), out['hw']
    assert _rows(out['screen']) == [want], out['screen']
    assert ['Cat6', 'no length', '1'] in out['cables'], out['cables']


def test_an_extension_keeps_its_note_off_the_home_runs(page):
    """A 25' extension off SNAKE A and CENTER's own 25' home run: two rows,
    "Cat6 Extension 25'" carrying "ext · SNAKE A" and "Cat6 25'" with no
    note - the merged totals never label the home run an extension."""
    pg, ids = page
    out = pg.evaluate("""async (ids) => {""" + HELPERS_JS + """
        await j('PUT', cardUrl, {portCables: {[cSock]: {ft: 25}, [aSock]: {ft: 25}}});
        const list = await rebuild();
        const res = {
            totals: list.totals.filter(r => /^Cat6/.test(r.type) && r.length === "25'"),
            aLabel: app.getPortLabelText(layer(ids.a), 1, 'primary'),
        };
        await j('PUT', cardUrl, {portCables: {[cSock]: {ft: 50}}});
        await rebuild();
        return res;
    }""", ids)
    assert _rows(out['totals']) == [
        ('Cat6', "25'", 1, ids['centerPortLabel'], ''),
        ('Cat6 Extension', "25'", 1, out['aLabel'], 'ext · SNAKE A')], out['totals']


def test_a_snake_is_labelled_by_its_ports_and_its_name_moves_to_notes(page):
    """The owner's rulings of 2026-10-21 on the card renamed VX A: a snake's
    LABEL is the port labels of its sockets, folded ("VX A-3 … A-5"), its
    own name in NOTES beside its size ("SNAKE B · 3 channel"); an
    extension and its barrel are labelled by the socket's own port label
    ("VX A-3"), the note still "ext · SNAKE B". SNAKE A (2 channel) and
    SNAKE B (3 channel), both 100', stay two rows everywhere - totals,
    the processor's pull list - and each keeps its own edit key."""
    pg, ids = page
    out = pg.evaluate("""async (ids) => {""" + HELPERS_JS + """
        const a = Number(aSock), b = Number(ids.sockets['WALL-B'][0]), c = Number(cSock);
        const free = [];
        for (let n = c + 1; free.length < 2 && n <= 16; n++) if (n !== a && n !== b) free.push(n);
        await j('PUT', cardUrl, {name: 'VX A'});
        await j('POST', '/api/snakes', {name: 'SNAKE B', ft: 100,
            members: [c, ...free].map(n => ({kind: 'card', id: ids.cardId, socket: n}))});
        const list = await rebuild();
        const snakeB = app.getShowSnakes().find(s => s.name === 'SNAKE B');
        const res = {
            a, b, c, free,
            sr: dataRows(list.positions[0].rows),
            center: dataRows(list.positions[1].rows),
            totals: list.totals.filter(r => r.type === 'Cat6 Snake'),
            hw: list.hardware.filter(h => h.kind === 'processor').map(h => h.rows.filter(r => r.type === 'Cat6 Snake'))[0],
            screen: dataRows(list.byScreen[String(ids.c)].rows),
            keys: list.positions.flatMap(p => p.rows).filter(r => r.type === 'Cat6 Snake').map(r => app.pullRowKey(r)),
            fold: [app._pullCompressNames(['VX A-1', 'VX A-2', 'VX A-3', 'VX A-4']),
                   app._pullCompressNames(['VX A-1', 'VX A-2']),
                   app._pullCompressNames(['VX A-1', 'VX A-2', 'VX A-3', 'VX B-1'])],
        };
        await j('DELETE', `/api/snakes/${snakeB.id}`);
        await j('PUT', cardUrl, {name: 'SR'});
        await rebuild();
        return res;
    }""", ids)
    assert out['fold'] == ['VX A-1 … A-4', 'VX A-1, VX A-2', 'VX A-1 … A-3, VX B-1'], out['fold']
    a, b, c, free = out['a'], out['b'], out['c'], out['free']
    assert free == [c + 1, c + 2], out
    snake_a = ('Cat6 Snake', "100'", 1, f'VX A-{a}, VX A-{b}', 'SNAKE A · 2 channel')
    snake_b = ('Cat6 Snake', "100'", 1, f'VX A-{c} … A-{c + 2}', 'SNAKE B · 3 channel')
    assert _rows(out['sr']) == [snake_a], out['sr']
    assert _rows(out['center']) == [
        ('Cat6 Barrel', 'EA', 1, f'VX A-{c}', ''),
        ('Cat6 Extension', "50'", 1, f'VX A-{c}', 'ext · SNAKE B'),
        snake_b], out['center']
    # never merged: two snakes of one length are two rows on every surface
    assert _rows(out['totals']) == [snake_a, snake_b], out['totals']
    assert sorted(_rows(out['hw'])) == sorted([snake_a, snake_b]), out['hw']
    assert snake_b in _rows(out['screen']), out['screen']
    assert len(set(out['keys'])) == 2 and all(k.startswith("Cat6 Snake|100'|snake:") for k in out['keys']), out['keys']
    assert ids['errors'] == []


def test_a_blank_cabinet_counts_nothing_on_a_hand_drawn_data_path(page):
    """A hand-drawn port across three of CENTER's cabinets, the middle one a
    legacy blank (blank, not hidden): the data reading - the resolved data
    path, the pull list's run, the canvas's port load - holds two
    cabinets, as the automatic walk does. Power's reading of the same path
    is unchanged."""
    pg, ids = page
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const c = app.project.layers.find(l => l.id === ids.c);
        const row0 = Math.min(...c.panels.map(p => p.row));
        const three = c.panels.filter(p => p.row === row0).sort((a, b) => a.col - b.col).slice(0, 3);
        const path = three.map(p => ({ row: p.row, col: p.col }));
        const saved = { flow: c.flowPattern, paths: c.customPortPaths };
        three[1].blank = true;
        c.flowPattern = 'custom';
        c.customPortPaths = { 1: path };
        try {
            return {
                data: app.getResolvedPathPanels(c, path, 'data').length,
                power: app.getResolvedPathPanels(c, path).length,
                run: app._pullPortRuns(c).map(r => r.panels.length),
                load: window.canvasRenderer._crossMemberLoadPanels(c, path).length,
            };
        } finally {
            delete three[1].blank;
            c.flowPattern = saved.flow;
            c.customPortPaths = saved.paths;
        }
    }""", ids)
    assert out == {'data': 2, 'power': 3, 'run': [2], 'load': 2}, out


def test_a_free_rows_side_reads_data_words_as_data(page):
    """Cat6 / Cat6A / Cat5e, etherCON, a barrel, a breakout box or a
    processor model are data; power words stay power."""
    pg, _ids = page
    sides = pg.evaluate("""() => Object.fromEntries([
        'Cat6', 'Cat6A', 'Cat5e', 'Cat6 Barrel', 'etherCON Snake', 'Barrel', 'XD', 'XD-S',
        'CVT10 Pro', 'CVT4K-S', 'H9', 'SQ200', 'MX40 Pro', 'RS12',
        'Multi', 'TRUE1 2fer', 'powerCON', 'L21-30', 'Edison', 'Socapex', 'Gaff'
    ].map(t => [t, window.app.pullGuessSide(t)]))""")
    data = ['Cat6', 'Cat6A', 'Cat5e', 'Cat6 Barrel', 'etherCON Snake', 'Barrel', 'XD', 'XD-S',
            'CVT10 Pro', 'CVT4K-S', 'H9', 'SQ200', 'MX40 Pro', 'RS12']
    assert {t: s for t, s in sides.items() if s == 'data'} == {t: 'data' for t in data}, sides


def test_a_free_rows_side_reads_whole_words_and_power_words_first(page):
    """Whole words only: "tac" inside Contactor / Stacking / Attachment /
    Stack is no TAC; "Optical isolator" is no data; a power word wins
    ("Socapex Snake", "Camlok Barrel"); a catalog model counts only as the
    whole name or its head before an equipment word ("S4 rack"), never
    before anything else ("S4 Spanset", "T1 Tape", "M2 bolt")."""
    pg, _ids = page
    power = ['Contactor', 'Stacking plate', 'Attachment', 'Ground Stack', 'Optical isolator',
             'Socapex Snake', 'Camlok Barrel', 'S4 Spanset', 'T1 Tape', 'M2 bolt', 'S40 bracket',
             'Edison → TRUE1 tail', 'CEE 16A → powerCON', '400 A cam set', 'Absen TRUE1 Long Power Jump']
    data = ['TAC 12', '12 Tac Fiber', 'opticalCON QUAD', 'MTP 24', '12G SDI', 'Ethernet',
            'Absen Long Data Jump', '16 port sending card + 2 OPT', '10G Single-Mode SFP',
            'S4', 'S4 rack', 'H9 spare (2)', 'XD rack', 'CVT Rack', 'Cat6 Snake']
    sides = pg.evaluate("(types) => Object.fromEntries(types.map(t => [t, window.app.pullGuessSide(t)]))",
                        power + data)
    assert {t: sides[t] for t in power} == {t: 'power' for t in power}, sides
    assert {t: sides[t] for t in data} == {t: 'data' for t in data}, sides


def test_a_fiber_cable_with_no_length_is_flagged_on_every_surface(page):
    """A TAC with no length on a CVT4K-S's link: the pull row says "no
    length" (as before), and so do the binder's CABLES THIS SCREEN, the
    strand map's title and Fiber Connections' cable cell. (Last in the
    module: deleting the box takes SNAKE A with it.)"""
    pg, ids = page
    out = pg.evaluate("""async (ids) => {""" + HELPERS_JS + """
        let st = await j('POST', `${cardUrl}/cvts`, {deviceId: 'novastar-cvt4k-s', pair: false});
        const boxId = st.processors[0].slots[0].card.cvts[0].id;
        st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12});
        const tac = st.fiberCables[st.fiberCables.length - 1];
        await j('PUT', `/api/processors/${ids.procId}/cvts/${boxId}/fiber-links/p1`, {cable: tac.id});
        const list = await rebuild();
        const proc = app._processorsResolved.find(p => p.id === ids.procId);
        const typeText = app.fiberCableTypeText(app.getFiberCable(tac.id));
        const res = {
            typeText,
            pull: list.totals.filter(r => r.type === typeText),
            cables: [ids.a, ids.b, ids.c].flatMap(id => cablesCells(list, layer(id)))
                .filter(c => c[0] === typeText),
            maps: app._bStrandMaps(proc).map(m => m.title),
            conn: app._bFiberConnectionRows(proc, 'H9').map(r => r.cells[1]),
        };
        await j('DELETE', `/api/processors/${ids.procId}/cvts/${boxId}`);
        await j('DELETE', `/api/fiber-cables/${tac.id}`);
        await rebuild();
        return res;
    }""", ids)
    t = out['typeText']
    assert [(r['type'], r['length'], r['notes']) for r in out['pull']] == [(t, '', 'no length')], out['pull']
    assert out['cables'] == [[t, 'no length', '1']], out['cables']
    assert len(out['maps']) == 1 and out['maps'][0].endswith(' · no length'), out['maps']
    assert any(c.endswith(' · no length') for c in out['conn']), out['conn']
    assert ids['errors'] == []


# ── 4. the SQ200 -> QD-S input fiber ─────────────────────────────────────

QD_SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    proj.beaches = []; proj.snakes = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 4, rows: 3,
                                                     cabinet_width: 200, cabinet_height: 200});
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'brompton', bitDepth: 8, frameRate: 60});
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('qd_fiber_setup');
    app.selectLayer(app.project.layers[0]);
    const foh = await app.createBeach('FOH');
    const sr = await app.createBeach('SR Beach');
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sq200', name: 'SQ A'});
    const pid = st.processors[st.processors.length - 1].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'brompton-card-qd-s'});
    const cid = st.processors.find(p => p.id === pid).slots[0].card.id;
    st = await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`, {deviceId: 'brompton-xd-s'});
    const box = st.processors.find(p => p.id === pid).slots[0].card.cvts[0].id;
    await j('PUT', `/api/processors/${pid}/cvts/${box}`, {beachId: sr.id});
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 300});
    const tac = st.fiberCables[st.fiberCables.length - 1].id;
    await j('PUT', `/api/processors/${pid}/cards/${cid}/fiber-links/p1`, {cable: tac});
    await app.refreshProcessors();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('QD Fiber Seed');
    return {pid, cid, box, tac, wall: wall.id, foh: foh.id, sr: sr.id};
}"""


def test_the_qd_s_input_fiber_goes_where_the_qd_s_is(page):
    """The SQ200's TAC onto the QD-S's IN 1, the QD-S's XD-S at SR Beach
    (the second beach): with no screen on it yet the TAC is pulled at SR
    Beach - where its box is, never the first position; with WALL placed
    on the XD-S it is still at SR Beach and on WALL's own reading, so the
    binder's CABLES THIS SCREEN lists it."""
    pg, _ids = page
    ids = pg.evaluate(QD_SEED_JS)
    pg.wait_for_timeout(600)
    out = pg.evaluate("""async (ids) => {
        const app = window.app;
        const rebuild = %s;
        const tacType = app.fiberCableTypeText(app.getFiberCable(ids.tac));
        const where = (list) => list.positions
            .filter(p => p.rows.some(r => r.type === tacType)).map(p => p.name);
        const loose = await rebuild();
        await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                     {layerId: String(ids.wall), cardId: ids.cid});
        const placed = await rebuild();
        const scr = placed.byScreen[String(ids.wall)] || {rows: []};
        return {
            tacType,
            loose: where(loose), placed: where(placed),
            onScreen: scr.rows.filter(r => r.type === tacType).map(r => [r.length, r.qty]),
            pins: (app.project.port_assignments.pins || []).length,
        };
    }""" % REBUILD_JS, ids)
    assert out['loose'] == ['SR Beach'], out
    assert out['pins'] > 0, out
    assert out['placed'] == ['SR Beach'], out
    assert out['onScreen'] == [["300'", 1]], out


def test_a_placed_port_with_no_length_says_so_on_the_binder(page):
    """CENTER's socket with no cable typed (owner, 2026-10-22): the data
    sheet's Ports HOME RUN says "Cat6 no length" as CABLES THIS SCREEN
    does, never a blank; the processor sheet's Snakes & home runs lists it,
    marked no length, as its Pull list does."""
    pg, ids = page
    out = pg.evaluate("""async (ids) => {""" + HELPERS_JS + """
        await j('PUT', cardUrl, {portCables: {}});
        await rebuild();
        const tables = [];
        const orig = app._bTableLines;
        app._bTableLines = function (book, spec) {
            tables.push({ title: spec.title, rows: (spec.rows || []).filter(r => r.cells).map(r => r.cells.slice()) });
            return orig.apply(this, arguments);
        };
        const opts = Object.assign(app.readBinderOptions(),
            { scope: { kind: 'show' }, hardware: true, pull: false, cover: false, wiring: false,
              sides: { power: false, data: true } });
        try { app.planBinder(opts); } finally { app._bTableLines = orig; }
        // a placed port's own socket, read off the assignment
        const pin = ((app._assignment && app._assignment.screens) || []).flatMap(s => s.ports || [])
            .find(p => p.cardId && p.port != null && !app.dataPortCable(p.cardId, p.port));
        const res = { tables, run: pin ? app.runText(null, { cardId: pin.cardId, port: pin.port }) : null,
                      none: app.runText(null), cards: (app._processorsResolved || []).length };
        await j('PUT', cardUrl, {portCables: {[cSock]: {ft: 50}}});
        await rebuild();
        return res;
    }""", ids)
    assert out['run'] in ('Cat6 no length', 'etherCON no length') and out['none'] == '', out
    ports = [r for t in out['tables'] if t['title'] == 'Ports' for r in t['rows']]
    assert [r for r in ports if 'Cat6 no length' in r], ports
    runs = [r for t in out['tables'] if t['title'] == 'Snakes & home runs' for r in t['rows']]
    assert [r for r in runs if r[1:] == ['cable', 'no length', 'Cat6']], runs
    assert ids['errors'] == []
