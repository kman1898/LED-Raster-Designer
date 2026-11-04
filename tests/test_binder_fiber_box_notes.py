"""The binder's FIBER page names, under each breakout box, the screens its
ports feed (app-binder-fiber.js _bfBoxNote) - QA beta.5, 2026-11-03.

  - On a grouped wall routed as one, every port belongs to the group, so
    the port's screen used to read the group's FIRST member: the boxes
    feeding the second member were labelled with the first one's name
    ("WALL SL" under the XDs feeding WALL SR, "Screen1" under the ones
    feeding Screen2 and Screen3). A box now names the screens
    whose cabinets its ports actually run to, cabinet by cabinet, the way
    the data sheets list a member's ports - a port crossing two members
    names both.
  - A box feeding many screens wraps its note onto as many lines as it
    takes, the rows growing to hold it, instead of cutting it to
    "WALL, TOWER 1, …" on a page that is mostly empty.

Synthetic show: an SX40 whose XD A, B and C all hang on one TAC; a group
UPSTAGE (UPSTAGE WEST + UPSTAGE EAST, routed as one) with its ports 1-2 on
XD A, port 3 - all on the east member's cabinets - on XD B and ports 4-6 on
XD C; four one-column TOWER screens on XD A too.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_binder_fiber_box_notes.py -v --browser chromium
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
        'fiber': True, 'titleBlock': True}

SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits; delete proj.snakes;
    await j('PUT', '/api/project', proj);
    const add = (name, cols, rows, x, y = 0) => j('POST', '/api/layer/add', {name, columns: cols, rows,
        cabinet_width: 340, cabinet_height: 340, offset_x: x, offset_y: y, processorType: 'brompton'});
    const west = await add('UPSTAGE WEST', 6, 2, 0);
    const east = await add('UPSTAGE EAST', 6, 2, 2040);
    const towers = [];
    for (let i = 0; i < 4; i++) towers.push(await add(`TOWER NUMBER ${i + 1}`, 1, 3, i * 340, 700));
    const p = await j('GET', '/api/project');
    p.groups = [{id: 'g1', name: 'UPSTAGE', layer_ids: [west.id, east.id]}];
    await j('PUT', '/api/project', p);
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: 'RACK'});
    const sx = st.processors[0].id;
    const card = st.processors[0].slots[0].card;
    const xds = card.cvts.map(b => b.id);
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 300, connector: 'LC duplex',
                                               link: {boxId: xds[0], key: 'p1'}});
    const tac = st.fiberCables[st.fiberCables.length - 1];
    for (const b of xds.slice(1, 3)) await j('PUT', `/api/processors/${sx}/cvts/${b}/fiber-links/p1`, {cable: tac.id});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('fiber_box_notes');
    await app.refreshProcessors();
    const refused = [];
    const place = (body) => app._assignmentRequest('/api/port-assignments/place-overflow', 'POST', body,
                                                   (d) => { refused.push(d); return true; }, 'Place');
    await place({layerId: String(west.id), cardId: card.id, lastIndex: 1});
    await place({layerId: String(west.id), cardId: card.id, boxId: xds[1], lastIndex: 2});
    await place({layerId: String(west.id), cardId: card.id, boxId: xds[2]});
    for (const t of towers) await place({layerId: String(t.id), cardId: card.id});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.selectLayer(app.project.layers[0]);
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Fiber Box Notes Seed');
    return {refused, sx, xds, west: west.id};
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    ids = pg.evaluate(SEED_JS)
    assert ids['refused'] == [], ids['refused']
    ids['errors'] = errors
    yield pg, ids
    context.close()


# Where each port of the group landed, and the screens each one's cabinets
# are on, read off the app - so the test states the seed it relies on.
PORTS_JS = """(west) => {
    const app = window.app;
    const layer = app.project.layers.find(l => l.id === west);
    const scr = app._assignment.screens.find(s => String(s.layerId) === String(west));
    const box = (n) => {
        const p = scr.ports.find(x => x.number === n);
        const home = app._bPortHome(p.cardId, p.port);
        return home && home.box ? app._bBoxTitle(home.box) : null;
    };
    return app._pullPortRuns(layer).map(r => ({
        num: r.num, box: box(r.num), on: [...new Set(r.layers.map(l => l.name))]}));
}"""

NOTES_JS = """() => {
    const app = window.app;
    return Object.fromEntries(app._fiberAllBoxes().map(({ box }) => [app._bBoxTitle(box), app._bfBoxNote(box)]));
}"""

PAGE_JS = """(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const i = plan.findIndex(p => p.kind === 'fiber');
    const r = app.renderBinderPage(opts, i);
    return {texts: r.texts, ops: r.record.ops.filter(o => o.op === 'text').map(o => o.text)};
}"""


def test_a_box_names_the_member_its_ports_feed(page):
    """XD B carries only port 3 of the group, whose cabinets are all on
    UPSTAGE EAST: it reads UPSTAGE EAST, never the group's first member.
    XD C carries ports 4-6, on both members: it names both. XD D feeds
    nothing and says nothing."""
    pg, ids = page
    ports = pg.evaluate(PORTS_JS, ids['west'])
    assert [(p['num'], p['box'], p['on']) for p in ports] == [
        (1, 'XD A', ['UPSTAGE WEST']), (2, 'XD A', ['UPSTAGE WEST', 'UPSTAGE EAST']),
        (3, 'XD B', ['UPSTAGE EAST']), (4, 'XD C', ['UPSTAGE WEST']),
        (5, 'XD C', ['UPSTAGE WEST', 'UPSTAGE EAST']), (6, 'XD C', ['UPSTAGE EAST'])], ports
    notes = pg.evaluate(NOTES_JS)
    assert notes['XD B'] == 'UPSTAGE EAST', notes
    assert notes['XD C'] == 'UPSTAGE WEST, UPSTAGE EAST', notes
    assert notes['XD A'] == ('UPSTAGE WEST, UPSTAGE EAST, TOWER NUMBER 1, TOWER NUMBER 2, '
                             'TOWER NUMBER 3, TOWER NUMBER 4'), notes
    assert notes['XD D'] == '', notes
    assert ids['errors'] == []


def test_a_long_note_wraps_whole_on_the_page(page):
    """XD A feeds six screens: its note is drawn on the Fiber page every
    line of it, nothing cut with an ellipsis, and nothing else on the page
    is cut either. XD B, under it, reads UPSTAGE EAST."""
    pg, ids = page
    out = pg.evaluate(PAGE_JS, OPTS)
    texts = out['ops']
    assert not [t for t in texts if t.endswith('…')], [t for t in texts if t.endswith('…')]
    a = texts.index('XD A')
    b = texts.index('XD B')
    note = ' '.join(texts[a + 1:b])
    assert note == ('UPSTAGE WEST, UPSTAGE EAST, TOWER NUMBER 1, TOWER NUMBER 2, '
                    'TOWER NUMBER 3, TOWER NUMBER 4'), texts[a:b]
    assert b - a - 1 >= 2, texts[a:b]           # wrapped, not squeezed onto one line
    assert texts[b + 1] == 'UPSTAGE EAST', texts[b:b + 3]
    assert ids['errors'] == []
