"""Every cell of a binder table prints at the table's one type size, and
every heading at the headings' one size - a cell or a heading too wide for
its column WRAPS at its words, or the table takes the room the sheet has;
nothing shrinks to fit and nothing is cut (QA beta.5, 2026-11-03, measured
off an exported binder):

  - the data sheet's Ports table: the BACKUP half's box band ("OPT1 / QUAD
    2 (opticalCON QUAD)") at 9.4 pt beside the PRIMARY's at 11.3, and one
    snake's heading at 8.96 pt where the next ones' were 9.43;
  - the processor page: the Breakout boxes' CARD column ("Sending Card 1")
    at 5 pt in a body of 8.6, its FIBER strand cut to "2 …", and Fiber
    connections' AT THE PROCESSOR / AT THE BREAKOUT headings at 5 and 5.8
    pt under OUTPUT's 7.6;
  - and, found on the same pass, the distro page's HOME RUN and CIRCUITS
    headings and its cells, and the pull pages' Screens headings.

Synthetic show, built the way those binders were: an H9 named RACK A with two
H_4xfiber cards ("Sending Card 1", backed up 1:1 by "Sending Card 2"), a
CVT4K-S on each (MAIN A, BACKUP A) on opticalCON QUAD cables QUAD 1 and QUAD 2,
a 16 x 8 wall on MAIN A with its returns on BACKUP A and four 4-channel snakes
across both boxes, three small screens beside it and every screen's multis
on one distro.

Measured two ways: every text the sheets draw is checked against the size
it asked for (the recorder's own font), and the cases above are read back
off the record - the ops the PDF prints - and held to their table's size.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_binder_one_size.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
        'scope': {'kind': 'show'}, 'cover': True, 'pull': True, 'hardware': True,
        'wiring': True, 'fiber': True, 'titleBlock': True}

SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits; delete proj.snakes;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'UPSTAGE WALL', columns: 16, rows: 8,
        cabinet_width: 256, cabinet_height: 128, processorType: 'novastar-armor'});
    for (const n of ['SIDE STAGE LEFT', 'SIDE STAGE RIGHT', 'DOWNSTAGE CENTER']) {
        await j('POST', '/api/layer/add', {name: n, columns: 3, rows: 2, cabinet_width: 256, cabinet_height: 128,
                                           offset_y: 1200, processorType: 'novastar-armor'});
    }
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9', name: 'RACK A'});
    const pid = st.processors[0].id;
    const cards = [], boxes = [];
    for (const i of [0, 1]) {
        st = await j('PUT', `/api/processors/${pid}/slots/${i}`, {deviceId: 'novastar-card-h-4xfiber'});
        const c = st.processors[0].slots.find(s => s.index === i).card.id;
        cards.push(c);
        await j('PUT', `/api/processors/${pid}/cards/${c}`, {name: `Sending Card ${i + 1}`});
        st = await j('POST', `/api/processors/${pid}/cards/${c}/cvts`,
                     {deviceId: 'novastar-cvt4k-s', name: i ? 'BACKUP A' : 'MAIN A'});
        boxes.push(st.processors[0].slots.find(s => s.index === i).card.cvts[0].id);
    }
    await j('PUT', `/api/processors/${pid}`, {redundancy: true});
    await j('PUT', `/api/processors/${pid}/cards/${cards[0]}`, {backupCardId: cards[1]});
    st = await j('POST', '/api/fiber-cables', {kind: 'opticalcon-quad', ft: 500, link: {boxId: boxes[0], key: 'p1'}});
    const q1 = st.fiberCables[st.fiberCables.length - 1];
    await j('PUT', `/api/fiber-cables/${q1.id}`, {name: 'QUAD 1'});
    st = await j('POST', '/api/fiber-cables', {kind: 'opticalcon-quad', ft: 500});
    const q2 = st.fiberCables[st.fiberCables.length - 1];
    await j('PUT', `/api/fiber-cables/${q2.id}`, {name: 'QUAD 2'});
    await j('PUT', `/api/processors/${pid}/cvts/${boxes[1]}/fiber-links/p1`, {cable: q2.id});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('one_size');
    await app.refreshProcessors();
    const refused = [];
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(wall.id), cardId: cards[0]}, (d) => { refused.push(d); return true; }, 'Place');
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    // four snakes, each two of the wall's ports and their two returns
    const scr = app._assignment.screens.find(s => String(s.layerId) === String(wall.id));
    const sockets = scr.ports.map(p => p.port);
    const back = sockets.map(s => app._pullBackedBy(cards[0], s));
    for (let k = 0; k < 4; k++) {
        const ks = [k * 2, k * 2 + 1];
        st = await j('POST', '/api/snakes', {name: `SNAKE ${'ABCD'[k]}`, ft: 125, members:
            ks.map(i => ({kind: 'cvt', id: boxes[0], socket: sockets[i]}))
              .concat(ks.map(i => ({kind: 'cvt', id: back[i].cvtId, socket: back[i].port})))});
        if (st.error) refused.push(st);
    }
    // every screen's multis on one distro
    const d = app.addDistro({name: 'DISTRO 1'});
    let n = 1;
    for (const l of app.project.layers) {
        const count = app.getSocaPlan(l).length;
        for (let k = 1; k <= count; k++) { app.setSocaDistro(l, k, d.id); app.setSocaNumber(l, k, n++); }
    }
    await Promise.all([...(app._inflightLayerPuts || [])]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.selectLayer(app.project.layers[0]);
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('One Size Seed');
    return {refused, ports: sockets.length};
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
    ids = pg.evaluate(SEED_JS)
    assert ids['refused'] == [] and ids['ports'] == 8, ids
    ids['errors'] = errors
    yield pg, ids
    context.close()


# Every sheet painted with _bText watched: each text a table draws - a
# cell, a band, a heading (asked at the cell's 24 px or the heading's 21) -
# with the size the recorder's font actually holds when it is drawn, and
# whether it came out cut.
WATCH_JS = """(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const out = [];
    const orig = app._bText;
    let sheet = null;
    app._bText = function(book, text, x, y, o) {
        const t = orig.call(this, book, text, x, y, o);
        const want = (o && o.size) || 24;
        if (book.page && book.page.painting && (want === 24 || want === 21)) {
            const m = /(\\d+(?:\\.\\d+)?)px/.exec(book.ctx.font);
            out.push({sheet, text: String(text), want, got: m ? parseFloat(m[1]) : want,
                      cut: String(t).endsWith('\\u2026') && !String(text).endsWith('\\u2026')});
        }
        return t;
    };
    try {
        plan.forEach((p, i) => { sheet = `${p.number} ${p.title}`; app.renderBinderPage(opts, i); });
    } finally { app._bText = orig; }
    return {sheets: plan.map(p => `${p.number} ${p.title}`), texts: out};
}"""

# One sheet's record: its text ops as the PDF prints them.
OPS_JS = """([opts, kind]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.kind === kind);
    if (i < 0) return null;
    return app.renderBinderPage(opts, i).record.ops.filter(o => o.op === 'text' && String(o.text).trim())
        .map(o => ({t: o.text, size: o.size, weight: o.weight}));
}"""


def test_no_table_text_is_shrunk_or_cut_on_any_sheet(page):
    """Every sheet of the set: the data sheets, the pull pages, the distro,
    the processor and the Fiber page. Each cell, band and heading is drawn
    at the size it asked for, and none ends in an ellipsis it did not
    have."""
    pg, ids = page
    out = pg.evaluate(WATCH_JS, OPTS)
    kinds = ' / '.join(out['sheets'])
    for want in ('Data', 'Pull', 'Distro', 'Processor', 'Fiber'):
        assert want in kinds, kinds
    bad = [t for t in out['texts'] if t['got'] < t['want'] - 0.01 or t['cut']]
    assert not bad, bad[:20]
    assert len(out['texts']) > 500, len(out['texts'])
    assert ids['errors'] == []


def _size(ops, text):
    hits = [o['size'] for o in ops if o['t'] == text]
    assert hits, (text, sorted({o['t'] for o in ops})[:80])
    return hits[0]


def test_the_ports_table_bands_print_at_the_cells_size(page):
    """The data sheet: both halves' box bands - the box, its input and its
    cable, its strands - and every snake's heading in both halves print at
    the size of the table's port cells."""
    pg, ids = page
    ops = pg.evaluate(OPS_JS, [OPTS, 'data'])
    cell = _size(ops, 'MAIN A-1')
    band = [o for o in ops if o['t'].startswith(('CVT4K-S MAIN A', 'CVT4K-S BACKUP A', 'SNAKE '))
            or 'QUAD' in o['t'] or o['t'] in ('OPT1', '1 Blue', '2 Orange')]
    assert len([o for o in band if o['t'].startswith('SNAKE ')]) >= 8, band
    assert {o['size'] for o in band} == {cell}, sorted({(o['t'], o['size']) for o in band})
    heads = [o for o in ops if o['t'] in ('PORT', 'HOME RUN', 'PANELS', 'OUTPUT')]
    assert len({o['size'] for o in heads}) == 1, heads
    assert not [o for o in ops if o['t'].endswith('…')]


def test_the_processor_page_prints_its_cells_and_headings_at_one_size(page):
    """The processor page: the Breakout boxes' CARD cells ("Sending Card 1",
    whole or wrapped at its words) and its FIBER strands at the cells' size,
    the strand never cut; Fiber connections' AT THE PROCESSOR and AT THE
    BREAKOUT at OUTPUT's size, wrapped where the column is narrow - never
    shrunk."""
    pg, ids = page
    ops = pg.evaluate(OPS_JS, [OPTS, 'processor'])
    cell = _size(ops, 'H_4xfiber')
    head = _size(ops, 'OUTPUT')
    cards = [o for o in ops if o['t'].startswith(('Sending', 'Card 1', 'Card 2'))]
    assert len(cards) >= 4, cards
    assert {o['size'] for o in cards} == {cell}, cards
    strands = [o for o in ops if o['t'] in ('1 Blue', '2 Orange')]
    assert strands and {o['size'] for o in strands} == {cell}, strands
    words = [o for o in ops if o['weight'] == 700 and o['t'] in (
        'AT THE PROCESSOR', 'AT THE BREAKOUT', 'AT THE', 'PROCESSOR', 'BREAKOUT', 'CARD', 'FIBER', 'TRUNK')]
    assert {'PROCESSOR', 'BREAKOUT'} & {w for o in words for w in o['t'].split()}, words
    assert {o['size'] for o in words} == {head}, words
    assert not [o for o in ops if o['t'].endswith('…')]
    assert ids['errors'] == []
