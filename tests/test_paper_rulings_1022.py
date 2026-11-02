"""The binder and pull-sheet paperwork (owner rulings, 2026-10-22).

  * A words cell (a distro box's NAME, a pull table's CABLE and LENGTH,
    Fiber Connections' CABLE) never folds to "+N more": it takes the lines
    it needs. A plain cell too long for its column (a distro's TYPE,
    SCREENS, a circuit's name) wraps at its words rather than being cut; a
    list member too wide for a line (a LABEL) wraps at its words; a column
    heading shrinks rather than being cut. Every sheet size.
  * The binder power sheet's Circuits table on a direct output prints the
    output's one cable ("30'+10' Edison → powerCON"), never the circuit
    stock.
  * Old pull-sheet edits: "Tru-1" as a word anywhere in the type is TRUE1;
    an old direct output key by its plug alone is the position's one
    "<plug> → <input>" row; an old row that is TWO rows now - a hide
    covers both, a count goes stale.
  * Old free rows read in today's spelling: TRUE1, etherCON, "... cable",
    on the pull pages, the xlsx and its GEAR LIST.
  * A placed data port with no length says "etherCON no length"; the
    processor sheet's Snakes & home runs lists it.
  * A distro fed thru another: its screens' FACTS read the service it
    counts on, the Distro row saying "thru" that distro.
  * "Feed: 50'" (said once); no dash on Data Wiring's note; a KV row
    never starts a line with " · ".

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_paper_rulings_1022.py -q --browser chromium
"""

import io
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

import pull_sheet  # noqa: E402


# ── the xlsx: an old free row in today's spelling ─────────────────────────

def test_the_workbook_writes_an_old_free_row_in_todays_spelling():
    openpyxl = pytest.importorskip('openpyxl')
    data, _ = pull_sheet.build_workbook({'positions': [{'name': 'P', 'rows': [
        {'type': 'Tru-1 Breakout', 'length': 'EA', 'qty': 1, 'label': '', 'notes': '', 'added': True},
        {'type': 'Ether-con Snake', 'length': "100'", 'qty': 1, 'label': '', 'notes': '', 'added': True},
        {'type': 'Edison → True1 tail', 'length': 'EA', 'qty': 2, 'label': '', 'notes': '', 'added': True},
        {'type': 'Pigtail', 'length': 'EA', 'qty': 1, 'label': '', 'notes': '', 'added': True},
    ]}]})
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb[pull_sheet.SHEET]
    written = [str(c.value) for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    for want in ('TRUE1 Breakout', 'etherCON Snake', 'Edison → TRUE1 cable', 'Pigtail'):
        assert want in written, (want, written)
    assert not [t for t in written if re.search(r'Tru-1|TRU-1|True1|Ether-con|\btail\b', t)], written
    gear = [wb['GEAR LIST'].cell(r, 1).value for r in range(4, 200) if wb['GEAR LIST'].cell(r, 1).value]
    # the rewritten words count as connectors in use: their families stay
    assert 'TRUE1 Breakout' in gear and 'etherCON Snake' in gear, gear
    assert not [t for t in gear if re.search(r'Tru-1|TRU-1|True1|Ether-con', str(t))], gear
    assert pull_sheet.free_row_spelling('Harting TRU-1 Breakout') == 'Harting TRUE1 Breakout'
    assert pull_sheet.free_row_spelling('TRUE1 Breakout') == 'TRUE1 Breakout'


# ── the browser ──────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_power_naming import DIST, ev, setup  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_function("() => window.app && window.app.project "
                         "&& typeof window.app.distroFace === 'function' && window.canvasRenderer")
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    pg.evaluate("""async () => {
        const app = window.app;
        await app._layerSavesSettled();
        const j = async (method, url, body) => (await fetch(url, {
            method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body) })).json();
        const proj = await j('GET', '/api/project');
        proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
        delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
        delete proj.services;
        await j('PUT', '/api/project', proj);
        await j('POST', '/api/layer/add', { name: 'WALL A', columns: 10, rows: 6,
            cabinet_width: 200, cabinet_height: 200 });
        await j('POST', '/api/layer/add', { name: 'WALL B', columns: 6, rows: 3,
            cabinet_width: 200, cabinet_height: 200, offset_x: 2600 });
        const p = await j('GET', '/api/project');
        app.project = p;
        app.selectLayer(p.layers[0]);
        app.renderLayers();
    }""")
    pg.wait_for_function("() => window.app.project.layers.length === 2")
    yield pg, errors
    context.close()


# A 40' cable: the circuit stock writes it as one 50' piece, the
# direct-output stock as 30' + 10'.
STOCK = {'perKind': True, 'ft': {'circuit': [50], 'direct': [10, 30]}, 'm': {}}

# Every sheet of the show at one sheet size: each text in paint order, and
# the tables and KV blocks the binder built.
BINDER_JS = """(o) => {
    const app = window.app;
    app._circuitTailCache = null;
    const tables = [], kv = [];
    const origT = app._bTableLines, origK = app._bKvLines;
    app._bTableLines = function (book, spec) {
        tables.push({ title: spec.title, cols: (spec.cols || []).map(c => c.title),
                      rows: (spec.rows || []).filter(r => r.cells).map(r => r.cells.slice()) });
        return origT.apply(this, arguments);
    };
    app._bKvLines = function (book, title, pairs) {
        kv.push({ title, pairs: pairs.map(p => p.slice()) });
        return origK.apply(this, arguments);
    };
    const opts = Object.assign(app.readBinderOptions(),
        { sheet: o.sheet || 'tabloid', scope: { kind: 'show' }, hardware: true, pull: true,
          cover: false, wiring: !!o.wiring, sides: { power: true, data: !!o.data } });
    let plan;
    const pages = [];
    try {
        plan = app.planBinder(opts);
        for (let i = 0; i < plan.length; i++) {
            const r = app.renderBinderPage(opts, i);
            pages.push({ title: plan[i].title, kind: plan[i].kind,
                         texts: r.record.ops.filter(op => op.op === 'text' && String(op.text).trim())
                                  .map(op => String(op.text)) });
        }
    } finally { app._bTableLines = origT; app._bKvLines = origK; }
    return { pages, tables, kv };
}"""

SHEETS = ('letter', 'tabloid', 'a4', 'a3', 'archc', 'archd')


def _cut_or_folded(pages):
    # (the title block's sheet title - "PULL · <every screen>" - is not a
    # table cell: it shrinks inside its box as it always did)
    return [(p['title'], t) for p in pages for t in p['texts']
            if (t.endswith('…') or re.search(r' \+\d+ more$', t))
            and not (t.isupper() and t.startswith(('PULL · ', 'DISTRO', 'PROCESSOR')))]


def test_words_cells_never_fold_and_a_long_member_wraps(page):
    """_bCellLines: a words cell takes the lines it needs, every word on
    them; a list member too wide for a line goes on at its words, and the
    fold still counts members."""
    pg, errors = page
    out = ev(pg, """
        const book = app._binderBook(app.readBinderOptions(), { dry: true });
        const words = app._bCellLines(book, 'STAGE LEFT DISTRO 1-1', 24, 400, 70, 2, true);
        const fiber = app._bCellLines(book, "OM3 (duplex) · no length", 24, 400, 60, 4, true);
        const label = app._bCellLines(book, 'STAGE LEFT DISTRO 1-1 → WALL A', 24, 400, 200, 3);
        const many = app._bCellLines(book, 'S1-1, S1-2, S1-3, S1-4, S1-5, S1-6, S1-7, S1-8', 24, 400, 120, 2);
        return { words, fiber, label, many };""")
    assert ' '.join(out['words']) == 'STAGE LEFT DISTRO 1-1' and len(out['words']) > 2, out
    assert not [t for t in out['words'] + out['fiber'] if 'more' in t], out
    assert ' '.join(out['fiber']).replace(' · ', ' ') .count('no length') == 1, out
    assert len(out['label']) > 1 and ' '.join(out['label']) == 'STAGE LEFT DISTRO 1-1 → WALL A', out
    assert not [t for t in out['label'] if t.endswith('…')], out
    # a real list still folds, counting its members
    assert out['many'][-1].endswith(' more') and len(out['many']) == 2, out
    shown = sum(len([m for m in line.split(', ') if re.match(r'^S1-\d', m)]) for line in out['many'])
    more = int(re.search(r'\+(\d+) more$', out['many'][-1]).group(1))
    assert shown + more == 8, out
    assert errors == [], errors


def test_the_distro_and_pull_sheets_print_long_names_and_types_whole(page):
    """STAGE LEFT DISTRO feeds WALL B on its Edison direct output (TYPE
    "Edison → powerCON") and WALL A on its multis; the box and screen
    names are long. On every sheet size no distro, pull or power sheet cuts
    a cell or folds a name to "+N more", and every name is there whole."""
    pg, errors = page
    dist = dict(DIST, name='STAGE LEFT DISTRO')
    setup(pg, distros=[dist], walls={
        'a': {'powerSocaDistro': {'1': 'd1', '2': 'd1'}, 'powerSocaNumber': {'1': 1, '2': 2},
              'powerSocaLengths': {'1': '100', '2': '100'}},
        'b': {'powerVoltage': 120, 'powerBreakoutType': 'soca-powercon', 'powerSocaSplits': [1],
              'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 3},
              'powerSocaLengths': {'1': '40'}}})
    ids = ev(pg, "const ids = [A.id, B.id]; A.name = 'UPSTAGE CENTER VIDEO WALL A';"
                 " B.name = 'DOWNSTAGE RIGHT SIDE SCREEN B'; app._circuitTailCache = null; return ids;")
    try:
        for sheet in SHEETS:
            b = pg.evaluate(BINDER_JS, {'sheet': sheet})
            pages = [p for p in b['pages'] if p['kind'] in ('distro', 'pull', 'power', 'totals')]
            assert pages, (sheet, [p['kind'] for p in b['pages']])
            assert _cut_or_folded(pages) == [], (sheet, _cut_or_folded(pages))
            distro = next(t for t in b['tables'] if t['cols'][:2] == ['name', 'type'])
            types = [r[1] for r in distro['rows']]
            assert 'Edison → powerCON' in types, (sheet, distro)
            # a wrapped cell is drawn a line at a time, in order
            texts = ' '.join(t for p in pages if p['kind'] == 'distro' for t in p['texts'])
            assert 'Edison → powerCON' in texts, (sheet, texts)
            for name in [r[0] for r in distro['rows']] + [r[3] for r in distro['rows']]:
                assert name in texts, (sheet, name, texts)
    finally:
        ev(pg, "const [a, b] = arg.map(id => app.project.layers.find(l => l.id === id));"
               " a.name = 'WALL A'; b.name = 'WALL B'; app._circuitTailCache = null; return null;", ids)
    assert errors == [], errors


def test_the_circuits_table_on_a_direct_output_prints_its_one_cable(page):
    """WALL B alone on PD 3 (Edison), its circuit's own 40' cable typed:
    the power sheet's Circuits table says "30'+10' Edison → powerCON"
    (the direct-output stock) as every other surface does, never the
    circuit stock's "50' Edison → powerCON"."""
    pg, errors = page
    setup(pg, distros=[DIST], walls={
        'b': {'powerVoltage': 120, 'powerBreakoutType': 'soca-powercon', 'powerSocaSplits': [1],
              'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 3},
              'powerSocaLengths': {'1': '40'}}})
    ev(pg, "app.project.cableStock = arg; return null;", STOCK)
    try:
        b1 = ev(pg, "const n = app.screenCircuits(B)[0].num;"
                    " B.powerCircuitCables = { [n]: { ft: 40, connector: null } };"
                    " app._circuitTailCache = null; return n;")
        want = ev(pg, "return app.directCircuitCable(B, arg).text;", b1)
        assert want == "30'+10' Edison → powerCON", want
        b = pg.evaluate(BINDER_JS, {})
        circuits = [t for t in b['tables'] if t['title'] == 'Circuits']
        cells = [r[4] for t in circuits for r in t['rows'] if len(r) == 5 and 'Edison' in str(r[4])]
        assert cells and all(c == want for c in cells), circuits
        texts = [t for p in b['pages'] if p['kind'] == 'power' for t in p['texts']]
        assert want in texts and "50' Edison → powerCON" not in texts, [t for t in texts if "Edison" in t or "30" in t]
    finally:
        ev(pg, "delete app.project.cableStock; B.powerCircuitCables = {};"
               " app._circuitTailCache = null; return null;")
    assert errors == [], errors


def test_feeder_said_once_and_kv_separators_end_their_line(page):
    """A distro with a feed and no input type: "Feed: 50'", never
    "Feed: Feed 50'". A KV value's " · " stays at the end of the line
    it follows and a leg's letter stays with its figure."""
    pg, errors = page
    setup(pg, distros=[dict(DIST, feeder={'ft': 50})], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}}})
    b = pg.evaluate(BINDER_JS, {})
    block = next(dict(k['pairs']) for k in b['kv'] if k['title'] == 'Distro')
    assert block.get('Power in') == "50'" and 'Feeder' not in block and 'Feed' not in block, block
    # the word is said once whatever the text leads with ("Power in" since
    # 2026-11-02)
    for old, want in (("Power in 50'", "50'"), ("L21-30 power in 50'", "L21-30 50'")):
        pg.evaluate("(t) => { window.app.feederText = () => t; }", old)
        try:
            b = pg.evaluate(BINDER_JS, {})
        finally:
            pg.evaluate("() => { delete window.app.feederText; }")
        block = next(dict(k['pairs']) for k in b['kv'] if k['title'] == 'Distro')
        assert block.get('Power in') == want, (old, block)
    words = ev(pg, "return app._bKvWords('SL · 400 A · X 87.1 · Y 81.4 · Z 20.7 A');")
    assert words == ['SL ·', '400 A ·', 'X 87.1 ·', 'Y 81.4 ·', 'Z 20.7 A'], words
    assert not [w for w in words if w.startswith('·')], words
    wiring = open(os.path.join(HERE, '..', 'src', 'static', 'js', 'app-binder-wiring.js'),
                  encoding='utf-8').read()
    assert 'no run to draw' in wiring and '— no run to draw' not in wiring
    assert errors == [], errors


def test_a_thru_fed_distros_screens_read_the_service_in_facts(page):
    """SR fed thru SL, SL on HOUSE: WALL B's FACTS (on SR) read "Service:
    HOUSE · ..." then a Distro row "SR · 400 A · thru SL · ..." (its
    rating beside its name, 2026-10-23)."""
    pg, errors = page
    sl = {'id': 'd1', 'name': 'SL', 'ratingA': 400, 'system': '120/208', 'serviceId': 's1'}
    sr = {'id': 'd2', 'name': 'SR', 'ratingA': 400, 'system': '120/208', 'feeder': {'from': 'd1'}}
    setup(pg, distros=[sl, sr], walls={
        'a': {'powerSocaDistro': {'1': 'd1'}, 'powerSocaNumber': {'1': 1}},
        'b': {'powerSocaDistro': {'1': 'd2'}, 'powerSocaNumber': {'1': 1}}})
    try:
        ev(pg, "app.project.services = [{ id: 's1', name: 'HOUSE', ratingA: 600, system: '120/208',"
               " voltage: 208, phase: 3 }]; app._distroFaceMemo = null; app._circuitTailCache = null;"
               " return null;")
        b = pg.evaluate(BINDER_JS, {})
        facts = [k['pairs'] for k in b['kv'] if k['title'] == 'Facts']
        b_facts = next(p for p in facts if any(k == 'Distro' and v.startswith('SR') for k, v in p))
        keys = [k for k, _ in b_facts]
        assert 'Service' in keys and keys.index('Service') < keys.index('Distro'), b_facts
        assert dict(b_facts)['Service'].startswith('HOUSE · 600 A'), b_facts
        assert dict(b_facts)['Distro'].startswith('SR · 400 A · thru SL'), b_facts
    finally:
        ev(pg, "delete app.project.services; app._distroFaceMemo = null; return null;")
    assert errors == [], errors


# ── old pull-sheet edits ─────────────────────────────────────────────────

def test_old_tru1_and_direct_output_keys_find_their_rows(page):
    pg, errors = page
    out = ev(pg, """
        return {
            l2130: app.pullEditKey("L21-30 Tru-1 Breakout|EA"),
            harting: app.pullEditKey("Harting TRU-1 Breakout|EA"),
            head: app.pullEditKey("Tru-1 Breakout|EA"),
            word: app.pullEditKey("Tru-10 Thing|EA"),
            cee: app._pullResolveEditKey("CEE 16A|50'", new Set(["CEE 16A → TRUE1|50'", "Multi|50'"])),
            tru: app._pullResolveEditKey("Tru-1|25'", new Set(["TRUE1 → powerCON|25'"])),
            own: app._pullResolveEditKey("Tru-1|25'", new Set(["TRUE1|25'", "TRUE1 → powerCON|25'"])),
            two: app._pullResolveEditKey("Edison|25'", new Set(["Edison → TRUE1|25'", "Edison → powerCON|25'"])),
            other: app._pullResolveEditKey("Edison|50'", new Set(["Edison → TRUE1|25'"])),
        };""")
    assert out['l2130'] == 'L21-30 TRUE1 Breakout|EA', out
    assert out['harting'] == 'Harting TRUE1 Breakout|EA', out
    assert out['head'] == 'TRUE1 Breakout|EA', out
    assert out['word'] == 'Tru-10 Thing|EA', out
    assert out['cee'] == "CEE 16A → TRUE1|50'", out
    assert out['tru'] == "TRUE1 → powerCON|25'", out
    assert out['own'] == "TRUE1|25'", out
    # more than one match, or none: it stays stale
    assert out['two'] == "Edison|25'" and out['other'] == "Edison|50'", out
    assert errors == [], errors


# A position whose old rows are two rows now, and its old free rows.
SPLIT_JS = """(mode) => {
    const app = window.app;
    const P = 'pos:split';
    const list = { positions: [{ key: P, name: 'SPLIT', rows: [
        { type: 'Cat6', length: "25'", qty: 2, label: 'A', notes: '', side: 'data' },
        { type: 'etherCON', length: "25'", qty: 3, label: 'B', notes: '', side: 'data' },
        { type: 'TRUE1 Power Jump', length: "6'", qty: 4, label: 'C', notes: '', side: 'power' },
        { type: 'powerCON Power Jump', length: "6'", qty: 5, label: 'D', notes: '', side: 'power' },
    ] }], totals: [] };
    app.project.pullSheetEdits = { positions: { [P]: {
        rows: [{ key: "Ether-con|25'", removed: true }, { key: "Tru-1 Power Jump|6'", qty: 9 }],
        added: [{ type: 'Tru-1 Breakout', length: 'EA', qty: 1, label: '', notes: '' },
                { type: 'L21-30 TRU-1 Breakout', length: 'EA', qty: 1, label: '', notes: '' },
                { type: 'Ether-con Snake', length: "100'", qty: 1, label: '', notes: '' },
                { type: 'Edison → True1 tail', length: 'EA', qty: 2, label: '', notes: '' }] } } };
    const orig = app.buildPullList;
    app.buildPullList = () => JSON.parse(JSON.stringify(list));
    try {
        const sheet = app.applyPullSheetEdits(JSON.parse(JSON.stringify(list)));
        const rows = sheet.positions[0].rows.map(r => [r.type, r.length, r.qty, r.side]);
        const stale = app.pullSheetStaleEdits(JSON.parse(JSON.stringify(list))).map(s => s.key);
        let restored = null;
        if (mode === 'restore') {
            app.restorePullSheetRow(P, "Cat6|25'");
            restored = app.applyPullSheetEdits(JSON.parse(JSON.stringify(list))).positions[0].rows
                .map(r => [r.type, r.length]);
        }
        return { rows, stale, restored,
                 stored: JSON.parse(JSON.stringify(app.project.pullSheetEdits || null)) };
    } finally {
        app.buildPullList = orig;
        delete app.project.pullSheetEdits;
    }
}"""


def test_an_old_row_that_is_two_rows_now_hide_covers_both_count_goes_stale(page):
    pg, errors = page
    out = pg.evaluate(SPLIT_JS, 'read')
    types = [(r[0], r[1]) for r in out['rows']]
    # the hide covers both 25' rows
    assert ('Cat6', "25'") not in types and ('etherCON', "25'") not in types, out['rows']
    # the count lands on neither jumper: it is stale, for the user to redo
    jumps = {r[0]: r[2] for r in out['rows'] if 'Power Jump' in r[0]}
    assert jumps == {'TRUE1 Power Jump': 4, 'powerCON Power Jump': 5}, out['rows']
    assert "Tru-1 Power Jump|6'" in out['stale'] and "Ether-con|25'" not in out['stale'], out['stale']
    # the old free rows in today's spelling, each on its side
    free = [(r[0], r[3]) for r in out['rows'] if r[0] not in ('TRUE1 Power Jump', 'powerCON Power Jump')]
    assert ('TRUE1 Breakout', 'power') in free and ('L21-30 TRUE1 Breakout', 'power') in free, free
    assert ('etherCON Snake', 'data') in free and ('Edison → TRUE1 cable', 'power') in free, free
    assert not [t for t, _ in free if re.search(r'Tru-1|TRU-1|True1|Ether-con|tail', t)], free
    # restoring one of the two leaves the other hidden
    out = pg.evaluate(SPLIT_JS, 'restore')
    assert ['Cat6', "25'"] in out['restored'] and ['etherCON', "25'"] not in out['restored'], out
    keys = [r['key'] for r in out['stored']['positions']['pos:split']['rows']]
    assert "etherCON|25'" in keys and "Ether-con|25'" not in keys, keys
    assert errors == [], errors
