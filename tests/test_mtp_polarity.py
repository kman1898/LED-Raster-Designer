"""An MTP's polarity and the legs it really delivers at the breakout box.

The owner, 2026-11-18 (superseding the MTP part of the 2026-10-06 rule
that printed an MTP's stored strands at both ends and "crosses inside"):

  - every MTP trunk carries a polarity, Type A, B or C, picked where the
    MTP is made (the New MTP step) and edited (its Edit); an MTP with none
    stored - every older show - reads Type A, and nothing is written to say
    so; the pick is one undo step and rides the save like the cable's
    other fields;
  - the binder (the processor page's Fiber connections and strand map, the
    Fiber page's drawing and tables) and the box's own Fiber section print
    the legs the MTP really delivers at the breakout box, by its count and
    polarity, with the send/receive swap at the breakout on top - never a
    second swap where the trunk already crosses the pair (mtp-polarity.js;
    tests/js/mtp_polarity.test.mjs pins the position math);
  - a count and polarity no maker's sheet documents (48, 16 or 32 in Type
    A or C, 8 fiber in any type) prints the processor's legs and "see
    cable map" at the far end: no number is made up.

Synthetic shows only: an SX40 whose XD A (strands 1-2) and XD B (3-4)
share MTP A, labelled by number, its count and polarity set per case.

Run locally (each session takes its own free port):
    python -m pytest tests/test_mtp_polarity.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _ok(resp, code=200):
    assert resp.status_code == code, resp.get_data(as_text=True)[:300]
    return resp.get_json()


def _refused(resp):
    assert resp.status_code == 400, resp.get_data(as_text=True)[:300]
    return resp.get_json()['error']


def _h9_box(client):
    """An H9 with a 4x fiber card and one CVT10: (processor id, box id)."""
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': 'novastar-card-h-4xfiber'}))
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts', json={'deviceId': 'novastar-cvt10'}), 201)
    card = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']
    return pid, card['cvts'][0]['id']


def _raw_cable(cable_id):
    import app as app_module
    return next(c for c in app_module.current_project.get('fiberCables') or [] if c.get('id') == cable_id)


# ── the server: stored, checked, read as Type A where none is stored ─────

def test_an_mtp_reads_type_a_until_another_is_picked(client):
    """A new MTP reads Type A and stores nothing for it; a pick is stored
    and read back; an MTP made with one keeps it. A TAC has no polarity."""
    _pid, box = _h9_box(client)
    st = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 24, 'ft': 300,
                                                    'link': {'boxId': box, 'key': 'p1'}}), 201)
    mtp = st['fiberCables'][-1]
    assert mtp['polarity'] == 'A', mtp
    assert 'polarity' not in _raw_cable(mtp['id'])
    st = _ok(client.put(f"/api/fiber-cables/{mtp['id']}", json={'polarity': 'B'}))
    assert next(c for c in st['fiberCables'] if c['id'] == mtp['id'])['polarity'] == 'B'
    assert _raw_cable(mtp['id'])['polarity'] == 'B'
    # an edit of another field leaves it as it is
    st = _ok(client.put(f"/api/fiber-cables/{mtp['id']}", json={'ft': 250}))
    assert next(c for c in st['fiberCables'] if c['id'] == mtp['id'])['polarity'] == 'B'
    st = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 12, 'polarity': 'C'}), 201)
    assert st['fiberCables'][-1]['polarity'] == 'C', st['fiberCables']
    st = _ok(client.post('/api/fiber-cables', json={'kind': 'tac', 'strands': 12}), 201)
    assert 'polarity' not in st['fiberCables'][-1], st['fiberCables']


def test_an_old_show_reads_type_a_and_is_not_rewritten(client):
    """A show saved before polarity - an MTP with no polarity - loads as
    Type A, and reading it writes nothing onto the cable."""
    _pid, box = _h9_box(client)
    mtp = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 24,
                                                     'link': {'boxId': box, 'key': 'p1'}}), 201)['fiberCables'][-1]
    project = client.get('/api/project').get_json()
    for c in project['fiberCables']:
        c.pop('polarity', None)
    _ok(client.put('/api/project', json=project))
    st = client.get('/api/processors').get_json()
    assert [c['polarity'] for c in st['fiberCables'] if c['id'] == mtp['id']] == ['A'], st['fiberCables']
    assert 'polarity' not in _raw_cable(mtp['id'])


def test_a_polarity_is_a_b_or_c_and_only_on_an_mtp(client):
    _pid, box = _h9_box(client)
    mtp = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 12,
                                                     'link': {'boxId': box, 'key': 'p1'}}), 201)['fiberCables'][-1]
    for bad in ('D', 'a', '', None, 1):
        why = _refused(client.put(f"/api/fiber-cables/{mtp['id']}", json={'polarity': bad}))
        assert why == 'An MTP’s polarity is Type A, B or C.', (bad, why)
    assert 'polarity' not in _raw_cable(mtp['id'])
    for kind in ('tac', 'opticalcon-duo', 'opticalcon-quad'):
        body = {'kind': kind, 'polarity': 'A'}
        if kind == 'tac':
            body['strands'] = 12
        assert _refused(client.post('/api/fiber-cables', json=body)) == 'Only an MTP has a polarity.', kind


# ── an 8 fiber MTP is Base-8; the pull sheet says the polarity ──────────

def _h9_boxes(client, n):
    """An H9 with a 4x fiber card and `n` CVT10s: (processor id, box ids)."""
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': 'novastar-card-h-4xfiber'}))
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    for _ in range(n):
        st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts', json={'deviceId': 'novastar-cvt10'}), 201)
    card = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']
    return pid, [b['id'] for b in card['cvts']]


def _links_of(client, box_id):
    for proc in client.get('/api/processors').get_json()['processors']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == box_id:
                    return box.get('fiberLinks')
    return None


def test_an_8_fiber_mtp_takes_1_to_4_then_9_to_12(client):
    """Owner, 2026-11-18: "8-fiber MTP uses the standard" - its strands are
    the plug positions 1-4 and 9-12, so four links take 1-2, 3-4, 9-10 and
    11-12, then it is full; 5-8 are no strands of it. A TAC of 8 keeps
    1-8."""
    pid, boxes = _h9_boxes(client, 4)
    mtp = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 8,
                                                     'link': {'boxId': boxes[0], 'key': 'p1'}}), 201)['fiberCables'][-1]
    for b in boxes[1:]:
        _ok(client.put(f'/api/processors/{pid}/cvts/{b}/fiber-links/p1', json={'cable': mtp['id']}))
    assert [_links_of(client, b)['p1']['strands'] for b in boxes] == [[1, 2], [3, 4], [9, 10], [11, 12]]
    why = _refused(client.put(f'/api/processors/{pid}/cvts/{boxes[0]}/fiber-links/p1',
                              json={'cable': mtp['id'], 'strands': [5, 6]}))
    assert why == 'MTP A has strands 1-4 and 9-12 - there is no strand 5.', why
    other, more = _h9_boxes(client, 1)
    why = _refused(client.put(f'/api/processors/{other}/cvts/{more[0]}/fiber-links/p1', json={'cable': mtp['id']}))
    assert why == 'MTP A is full: every strand is in use.', why
    # a strand name is by position too
    why = _refused(client.put(f"/api/fiber-cables/{mtp['id']}", json={'strandName': {'strand': 5, 'name': 'X'}}))
    assert why == 'There is no strand 5 on this cable.', why
    _ok(client.put(f"/api/fiber-cables/{mtp['id']}", json={'strandName': {'strand': 9, 'name': 'SR'}}))
    # a TAC of 8 is 1-8
    tac = _ok(client.post('/api/fiber-cables', json={'kind': 'tac', 'strands': 8,
                                                     'link': {'boxId': more[0], 'key': 'p1'}}), 201)['fiberCables'][-1]
    _ok(client.put(f'/api/processors/{other}/cvts/{more[0]}/fiber-links/p1',
                   json={'cable': tac['id'], 'strands': [5, 6]}))
    assert _links_of(client, more[0])['p1']['strands'] == [5, 6]


def test_a_count_change_keeps_the_strands_in_use(client):
    """An MTP 12 with a link on 5-6 cannot become an 8 (it has no 5-8),
    one on 9-10 can, and keeps them; an 8 grows back to 12 as it is."""
    pid, boxes = _h9_boxes(client, 2)
    mtp = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 12,
                                                     'link': {'boxId': boxes[0], 'key': 'p1'}}), 201)['fiberCables'][-1]
    url = f"/api/fiber-cables/{mtp['id']}"
    _ok(client.put(f'/api/processors/{pid}/cvts/{boxes[1]}/fiber-links/p1',
                   json={'cable': mtp['id'], 'strands': [5, 6]}))
    why = _refused(client.put(url, json={'strands': 8}))
    assert why == ('Strand 5 is in use, and an 8 fiber MTP has no strand 5: its strands are 1-4 '
                   'and 9-12. Move that link first.'), why
    _ok(client.put(f'/api/processors/{pid}/cvts/{boxes[1]}/fiber-links/p1',
                   json={'cable': mtp['id'], 'strands': [9, 10]}))
    _ok(client.put(url, json={'strands': 8}))
    assert _links_of(client, boxes[1])['p1']['strands'] == [9, 10]
    _ok(client.put(url, json={'strands': 12}))
    assert _links_of(client, boxes[1])['p1']['strands'] == [9, 10]
    # past the count still says it the old way
    assert _refused(client.put(url, json={'strands': 6})).startswith('Strand 10 is in use - the count cannot')


def test_an_old_8_fiber_mtp_reads_its_5_to_8_as_9_to_12(client):
    """A show saved when an 8 fiber MTP was numbered 1-8: a link on 5-6 is
    the same fibers on 9-10 once loaded, a name typed on 5 moves to 9, and
    a TAC of 8 is left alone. Loading it again - an undo snapshot from
    before, or the file twice - reads the same: the pass is idempotent."""
    import copy
    pid, boxes = _h9_boxes(client, 2)
    mtp = _ok(client.post('/api/fiber-cables', json={'kind': 'mtp', 'strands': 8,
                                                     'link': {'boxId': boxes[0], 'key': 'p1'}}), 201)['fiberCables'][-1]
    tac = _ok(client.post('/api/fiber-cables', json={'kind': 'tac', 'strands': 8,
                                                     'link': {'boxId': boxes[1], 'key': 'p1'}}), 201)['fiberCables'][-1]
    old = client.get('/api/project').get_json()
    card = next(p for p in old['processors'] if p['id'] == pid)['slots'][0]['card']
    by = {b['id']: b for b in card['cvts']}
    by[boxes[0]]['fiberLinks']['p1']['strands'] = [5, 6]
    by[boxes[1]]['fiberLinks']['p1']['strands'] = [5, 6]
    for c in old['fiberCables']:
        if c['id'] == mtp['id']:
            c['strandNames'] = {'5': 'SR main', '2': 'kept'}
        if c['id'] == tac['id']:
            c['strandNames'] = {'5': 'tac five'}
    for _ in range(2):
        _ok(client.put('/api/project', json=copy.deepcopy(old)))
        assert _links_of(client, boxes[0])['p1']['strands'] == [9, 10]
        assert _links_of(client, boxes[1])['p1']['strands'] == [5, 6]
        cables = {c['id']: c for c in client.get('/api/processors').get_json()['fiberCables']}
        assert cables[mtp['id']]['strandNames'] == {'9': 'SR main', '2': 'kept'}, cables[mtp['id']]
        assert cables[tac['id']]['strandNames'] == {'5': 'tac five'}, cables[tac['id']]
    # the migrated show PUT back (an undo after the load) is unchanged
    now = client.get('/api/project').get_json()
    _ok(client.put('/api/project', json=copy.deepcopy(now)))
    assert _links_of(client, boxes[0])['p1']['strands'] == [9, 10]
    # the file load funnel the same
    _ok(client.post('/api/project', json=copy.deepcopy(old)))
    assert _links_of(client, boxes[0])['p1']['strands'] == [9, 10]


def test_the_pull_words_say_the_polarity():
    import processor_catalog as catalog
    assert catalog.fiber_cable_type_text({'kind': 'mtp', 'strands': 24}) == 'MTP 24 Type A'
    assert catalog.fiber_cable_type_text({'kind': 'mtp', 'strands': 24, 'polarity': 'B'}) == 'MTP 24 Type B'
    assert catalog.fiber_cable_type_text({'kind': 'mtp', 'strands': 12, 'polarity': 'C'},
                                         'single') == 'MTP 12 Type C · Single mode'
    assert catalog.fiber_cable_type_text({'kind': 'tac', 'strands': 12, 'connector': 'ST'}) == 'TAC 12 · ST'
    assert catalog.fiber_cable_positions({'kind': 'mtp', 'strands': 8}) == [1, 2, 3, 4, 9, 10, 11, 12]
    assert catalog.fiber_cable_positions({'kind': 'tac', 'strands': 8}) == list(range(1, 9))
    assert catalog.fiber_positions_text([1, 2, 3, 4, 9, 10, 11, 12]) == '1-4 and 9-12'
    assert catalog.fiber_positions_text(list(range(1, 13))) == '1-12'


# ── the browser: the binder, the Fiber page, the box's Fiber section ─────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

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
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: 'WALL SR'});
    const sx = st.processors[st.processors.length - 1].id;
    const xds = st.processors[st.processors.length - 1].slots[0].card.cvts.map(b => b.id);
    st = await j('POST', '/api/fiber-cables', {kind: 'mtp', strands: 24, ft: 300,
                                               link: {boxId: xds[0], key: 'p1'}});
    const mtp = st.fiberCables[st.fiberCables.length - 1];
    await j('PUT', `/api/processors/${sx}/cvts/${xds[1]}/fiber-links/p1`, {cable: mtp.id});
    await j('PUT', `/api/fiber-cables/${mtp.id}`, {labels: 'numbers'});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('mtp_polarity_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('MTP Polarity Seed');
    return {sx, xds, mtp: mtp.id};
}"""

# The cable set to a count and polarity, through the server, and the app
# holding it.
SET_JS = """async ([id, body]) => {
    await fetch(`/api/fiber-cables/${id}`, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    await window.app.refreshProcessors();
    window.app.renderHardwareDock();
    const c = window.app.getFiberCable(id);
    return {strands: c.strands, polarity: c.polarity, labels: c.labels};
}"""

# Everything the binder and the box's sheet print for the MTP's links.
READ_JS = """([sx, xdA, xdB, id]) => {
    const app = window.app;
    const proc = app._processorsResolved.find(p => p.id === sx);
    const rows = app._bFiberConnectionRows(proc).filter(r => r.link && r.link.cable && r.link.cable.id === id);
    const at = (box) => rows.find(r => r.link.box.id === box);
    const conn = (r) => ({p: r.cells[2], b: r.cells[4],
                          bParts: (r.parts[4] || []).map(x => ({text: x.text, swatch: !!x.swatch}))});
    const map = app._bStrandMaps(proc).find(m => m.title.startsWith('Strand map · MTP A'));
    const page = app.binderFiberPage();
    const links = page.procs.flatMap(p => p.links).filter(x => x.cableId === id);
    const pageMap = page.cables.find(c => c.id === id);
    return {
        a: conn(at(xdA)), b: conn(at(xdB)),
        map: {title: map.title, note: map.note, cols: map.cols.map(c => c.title),
              rows: map.rows.slice(0, 4).map(r => r.cells)},
        page: links.map(x => ({box: x.box, p: x.atProcessor, b: x.atBreakout})),
        pageMap: {title: pageMap.title, rows: pageMap.rows.filter(r => r.cells).map(r => r.cells)},
    };
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

SECTION_JS = """([boxId, key]) => {
    const row = document.querySelector(`[data-lrd-fiber-link="${boxId}:${key}"]`);
    if (!row) return null;
    const tag = row.querySelector('.hw-dock-fiber-polarity');
    return {chips: [...row.querySelectorAll('.hw-dock-fiber-strand')].map(c => c.textContent),
            titles: [...row.querySelectorAll('.hw-dock-fiber-strand')].map(c => c.title),
            tag: tag ? tag.textContent : null};
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
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    # a processor with no screens is off the binder (owner, 2026-11-17)
    from test_hidden_screen_binder import FEED_JS
    pg.evaluate(FEED_JS)
    settled(pg, lambda: pg.evaluate(
        "(sx) => !!(window.app._processorsResolved || []).find(p => p.id === sx)", ids['sx']),
        bool, 5000)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _set(pg, ids, **body):
    got = pg.evaluate(SET_JS, [ids['mtp'], body])
    for k, v in body.items():
        assert got[k] == v, (body, got)


def _read(pg, ids):
    return pg.evaluate(READ_JS, [ids['sx'], ids['xds'][0], ids['xds'][1], ids['mtp']])


def _section(pg, box, key='p1'):
    assert pg.evaluate(OPEN_SHEET_JS, box), f'the cable sheet of {box} did not open'
    return settled(pg, lambda: pg.evaluate(SECTION_JS, [box, key]), lambda v: v is not None)


# count, polarity -> XD A's legs at the breakout (strands 1 · 2 at the
# processor), XD B's (3 · 4), and the strand map's leg for strands 1-4
DOCUMENTED = [
    (12, 'A', ['2', '1'], ['4', '3'], ['1', '2', '3', '4']),
    (24, 'A', ['14', '13'], ['16', '15'], ['13', '14', '15', '16']),
    (24, 'B', ['23', '24'], ['21', '22'], ['24', '23', '22', '21']),
    (24, 'C', ['13', '14'], ['15', '16'], ['14', '13', '16', '15']),
    (16, 'B', ['15', '16'], ['13', '14'], ['16', '15', '14', '13']),
    (32, 'B', ['15', '16'], ['13', '14'], ['16', '15', '14', '13']),
    # Base-8 (owner, 2026-11-18): strands 1-4 and 9-12
    (8, 'A', ['2', '1'], ['4', '3'], ['1', '2', '3', '4']),
    (8, 'B', ['11', '12'], ['9', '10'], ['12', '11', '10', '9']),
]


@pytest.mark.parametrize('count,polarity,leg_a,leg_b,legs', DOCUMENTED,
                         ids=[f'{c}{p}' for c, p, *_ in DOCUMENTED])
def test_the_binder_prints_the_legs_the_mtp_delivers(page, count, polarity, leg_a, leg_b, legs):
    """Fiber connections, the processor's strand map, the Fiber page's
    drawing and its strand map all read the same legs at the breakout: the
    far end's by the count and polarity, the pair flipped there unless the
    trunk crossed it already. The processor end is the stored order, and
    an MTP never says "crosses inside"."""
    pg, ids = page
    _set(pg, ids, strands=count, polarity=polarity)
    out = _read(pg, ids)
    assert out['a']['p'] == '1 · 2' and out['a']['b'] == ' · '.join(leg_a), out['a']
    assert out['b']['p'] == '3 · 4' and out['b']['b'] == ' · '.join(leg_b), out['b']
    # a cable labelled by number has no swatches, at either end
    assert [x['swatch'] for x in out['a']['bParts']] == [False, False], out['a']
    m = out['map']
    assert m['title'] == f"Strand map · MTP A · MTP {count} Type {polarity} · 300'", m
    assert m['cols'] == ['strand', 'at the breakout', 'link', 'box ports'], m
    assert [r[0] for r in m['rows']] == ['1', '2', '3', '4'], m
    assert [r[1] for r in m['rows']] == legs, m
    assert [r[2] for r in m['rows']] == ['XD A · X1', 'XD A · X1', 'XD B · X1', 'XD B · X1'], m
    assert m['note'] == '', m
    assert out['page'] == [{'box': 'XD A', 'p': ['1', '2'], 'b': leg_a},
                           {'box': 'XD B', 'p': ['3', '4'], 'b': leg_b}], out['page']
    assert out['pageMap']['title'] == m['title'], out['pageMap']
    assert [r[0] for r in out['pageMap']['rows']] == ['1 · 2', '3 · 4'], out['pageMap']
    assert [r[3] for r in out['pageMap']['rows']] == [' · '.join(leg_a), ' · '.join(leg_b)], out['pageMap']
    assert 'crosses inside' not in repr(out), out
    assert ids['errors'] == []


UNDOCUMENTED = [(48, 'A'), (72, 'B'), (16, 'A'), (32, 'C'), (8, 'C')]


@pytest.mark.parametrize('count,polarity', UNDOCUMENTED, ids=[f'{c}{p}' for c, p in UNDOCUMENTED])
def test_an_undocumented_mtp_says_see_cable_map(page, count, polarity):
    """No maker's sheet maps it: the processor end prints its legs and the
    breakout end "see cable map" - no number is made up. The strand map
    keeps its strands and says it under its title. An 8 fiber MTP in
    Type C is one of them."""
    pg, ids = page
    _set(pg, ids, strands=count, polarity=polarity)
    out = _read(pg, ids)
    assert (out['a']['p'], out['a']['b']) == ('1 · 2', 'see cable map'), out['a']
    assert (out['b']['p'], out['b']['b']) == ('3 · 4', 'see cable map'), out['b']
    m = out['map']
    assert m['title'] == f"Strand map · MTP A · MTP {count} Type {polarity} · 300'", m
    assert m['cols'] == ['strand', 'link', 'box ports'], m
    assert m['note'] == 'At the breakout box: see cable map', m
    assert [r[0] for r in m['rows']] == ['1', '2', '3', '4'], m
    assert out['page'] == [{'box': 'XD A', 'p': ['1', '2'], 'b': ['see cable map']},
                           {'box': 'XD B', 'p': ['3', '4'], 'b': ['see cable map']}], out['page']
    assert [r[3] for r in out['pageMap']['rows']] == ['see cable map'] * 2, out['pageMap']
    assert ids['errors'] == []


def test_colour_legs_are_named_and_swatched_by_their_own_number(page):
    """On a cable in colours each leg at the breakout is named and swatched
    by its own number there: MTP-24 Type A's 1 Blue · 2 Orange arrive on
    13 and 14, read 14 Orange/Black · 13 Blue/Black."""
    pg, ids = page
    _set(pg, ids, strands=24, polarity='A', labels='colors')
    try:
        out = _read(pg, ids)
        assert out['a']['p'] == '1 Blue · 2 Orange', out['a']
        assert out['a']['b'] == '14 Orange/Black · 13 Blue/Black', out['a']
        assert [x['swatch'] for x in out['a']['bParts']] == [True, True], out['a']
        assert out['map']['rows'][0][:2] == ['1 Blue', '13 Blue/Black'], out['map']
    finally:
        _set(pg, ids, labels='numbers')
    assert ids['errors'] == []


def test_the_box_fiber_section_reads_the_legs_at_the_box(page):
    """The box's own Fiber section: an MTP-24 Type A link on 1 · 2 shows
    the legs it plugs in here, 14 · 13, its polarity beside them; each chip
    still names its strand at the processor in its tip. A Type B trunk's
    pair arrives crossed and reads as delivered. A count with no documented
    map keeps the processor's strands and says to read the cable's map."""
    pg, ids = page
    a = ids['xds'][0]
    _set(pg, ids, strands=24, polarity='A')
    sec = _section(pg, a)
    assert sec['chips'] == ['14', '13'] and sec['tag'] == 'Type A', sec
    assert sec['titles'][0].startswith('Leg 14 at this box: strand 2 of MTP A at the processor'), sec
    _set(pg, ids, polarity='B')
    sec = settled(pg, lambda: pg.evaluate(SECTION_JS, [a, 'p1']), lambda v: v and v['tag'] == 'Type B')
    assert sec['chips'] == ['23', '24'], sec
    _set(pg, ids, strands=48, polarity='A')
    sec = settled(pg, lambda: pg.evaluate(SECTION_JS, [a, 'p1']), lambda v: v and 'see cable map' in (v['tag'] or ''))
    assert sec['chips'] == ['1', '2'], sec
    assert sec['tag'] == 'Type A · processor legs · see cable map', sec
    _set(pg, ids, strands=24, polarity='A')
    assert ids['errors'] == []


def test_the_polarity_picker_is_one_undo_step(page):
    """Edit on an MTP link offers "polarity" Type A, B, C - Type A on a
    cable that never had one picked. A pick is one history entry; undo
    puts Type A back and redo Type B, on the server and on the box's
    chips."""
    pg, ids = page
    a, mtp = ids['xds'][0], ids['mtp']
    _set(pg, ids, strands=24, polarity='A')
    _section(pg, a)
    pg.locator(f'[data-lrd-field="fiber-edit-{a}-p1"]').click()
    sel = pg.locator(f'[data-lrd-field="fiber-cable-polarity-{mtp}"]')
    sel.wait_for()
    assert sel.evaluate("s => [...s.options].map(o => o.textContent)") == ['Type A', 'Type B', 'Type C']
    assert sel.input_value() == 'A'
    label = sel.evaluate("s => s.parentElement.querySelector('.hw-dock-fiber-dim').textContent")
    assert label == 'polarity', label
    index = pg.evaluate('() => window.app.historyIndex')

    def served():
        st = pg.evaluate("async () => (await (await fetch('/api/processors')).json())")
        return next(c['polarity'] for c in st['fiberCables'] if c['id'] == mtp)

    sel.select_option('B')
    assert settled(pg, served, lambda v: v == 'B', 8000) == 'B'
    settled(pg, lambda: pg.evaluate('() => window.app.historyIndex'), lambda v: v == index + 1)
    assert pg.evaluate('() => window.app.history[window.app.historyIndex].action') == 'Set MTP Polarity'
    assert pg.evaluate('() => window.app.historyIndex') == index + 1
    sec = settled(pg, lambda: pg.evaluate(SECTION_JS, [a, 'p1']), lambda v: v and v['tag'] == 'Type B')
    assert sec['chips'] == ['23', '24'], sec
    pg.evaluate('() => window.app.undo()')
    assert settled(pg, served, lambda v: v == 'A', 8000) == 'A'
    sec = settled(pg, lambda: pg.evaluate(SECTION_JS, [a, 'p1']), lambda v: v and v['tag'] == 'Type A')
    assert sec['chips'] == ['14', '13'], sec
    pg.evaluate('() => window.app.redo()')
    assert settled(pg, served, lambda v: v == 'B', 8000) == 'B'
    pg.evaluate("() => { window.app._fiberEdit = null; window.app.renderHardwareDock(); }")
    _set(pg, ids, polarity='A')
    assert ids['errors'] == []


def test_new_mtp_picks_its_polarity_with_its_length(page):
    """The New MTP step asks the strand count, then the length with the
    polarity beside it, Type A until another is picked: Create makes the
    MTP on the link with it, in one undo step."""
    pg, ids = page
    c = ids['xds'][2]
    _section(pg, c)
    index = pg.evaluate('() => window.app.historyIndex')
    pg.locator(f'[data-lrd-field="fiber-link-cable-{c}-p1"]').select_option('new:mtp')
    pg.locator(f'[data-lrd-field="fiber-new-{c}-p1-strands-12"]').click()
    pick = pg.locator(f'[data-lrd-field="fiber-new-{c}-p1-polarity"]')
    pick.wait_for()
    assert pick.input_value() == 'A'
    pg.locator(f'[data-lrd-field="fiber-new-{c}-p1-ft"]').fill('200')
    pick.select_option('C')
    pg.locator(f'[data-lrd-field="fiber-new-{c}-p1-ft-next"]').click()

    def made():
        st = pg.evaluate("async () => (await (await fetch('/api/processors')).json())")
        return [x for x in st['fiberCables'] if x['id'] != ids['mtp'] and x['kind'] == 'mtp']

    got = settled(pg, made, lambda v: len(v) == 1, 8000)
    assert [(x['strands'], x['ft'], x['polarity']) for x in got] == [(12, 200, 'C')], got
    settled(pg, lambda: pg.evaluate('() => window.app.historyIndex'), lambda v: v == index + 1)
    assert pg.evaluate('() => window.app.history[window.app.historyIndex].action') == 'New MTP'
    # Type C crosses each pair: 1 · 2 arrive on 2 · 1 and read 1 Blue · 2 Orange
    sec = settled(pg, lambda: pg.evaluate(SECTION_JS, [c, 'p1']), lambda v: v and v['tag'] == 'Type C')
    assert sec['chips'] == ['1 Blue', '2 Orange'], sec
    pg.evaluate('() => window.app.undo()')
    assert settled(pg, made, lambda v: v == [], 8000) == []
    assert ids['errors'] == []


PAINT_JS = """(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const out = [];
    plan.forEach((p, i) => {
        if (p.kind !== 'fiber' && p.kind !== 'processor') return;
        out.push({kind: p.kind, title: p.title, texts: app.renderBinderPage(opts, i).texts});
    });
    return out;
}"""


def test_the_painted_sheets_carry_the_legs(page):
    """On paper: the Fiber page and the processor's page print MTP-24
    Type A's strand map under its polarity, its AT THE BREAKOUT column,
    and nothing says "crosses inside"."""
    pg, ids = page
    _set(pg, ids, strands=24, polarity='A')
    opts = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': False, 'data': True},
            'scope': {'kind': 'show'}, 'cover': False, 'pull': True, 'hardware': True,
            'titleBlock': True, 'fiber': True}
    pages = pg.evaluate(PAINT_JS, opts)
    kinds = [p['kind'] for p in pages]
    assert 'fiber' in kinds and 'processor' in kinds, kinds
    title = "STRAND MAP · MTP A · MTP 24 TYPE A · 300'"
    for p in pages:
        texts = p['texts']
        assert not [t for t in texts if 'crosses inside' in t.lower()], p['title']
        assert not [t for t in texts if t.endswith(chr(0x2026))], p['title']
    fiber = next(p for p in pages if p['kind'] == 'fiber')
    assert title in fiber['texts'], fiber['texts'][:80]
    proc = next((p for p in pages if p['kind'] == 'processor' and title in p['texts']), None)
    assert proc, [p['texts'][:40] for p in pages]
    assert 'AT THE BREAKOUT' in proc['texts'], proc['texts']
    # Fiber connections' AT THE BREAKOUT: a strand to a line, logged whole
    assert '14 13' in proc['texts'] and '16 15' in proc['texts'], proc['texts']
    assert ids['errors'] == []


def test_an_8_fiber_mtp_shows_its_strands_by_position(page):
    """Owner, 2026-11-18: an 8 fiber MTP is Base-8 everywhere it is shown.
    Its strand map and the Fiber page's spares walk 1-4 and 9-12, named
    and coloured by position (9 Yellow to 12 Aqua); a strand chip's pick
    offers those eight; the cable's editor names those eight."""
    pg, ids = page
    a, mtp = ids['xds'][0], ids['mtp']
    _set(pg, ids, strands=8, polarity='A', labels='colors')
    try:
        out = pg.evaluate("""([sx, id]) => {
            const app = window.app;
            const proc = app._processorsResolved.find(p => p.id === sx);
            const map = app._bStrandMaps(proc).find(m => m.title.startsWith('Strand map · MTP A'));
            const page = app.binderFiberPage();
            return {rows: map.rows.map(r => r.cells.slice(0, 2)), title: map.title,
                    spare: page.cables.find(c => c.id === id).spare,
                    positions: app.fiberStrandPositions(app.getFiberCable(id))};
        }""", [ids['sx'], mtp])
        assert out['title'] == "Strand map · MTP A · MTP 8 Type A · 300'", out
        names = ['1 Blue', '2 Orange', '3 Green', '4 Brown', '9 Yellow', '10 Violet', '11 Rose', '12 Aqua']
        assert [r[0] for r in out['rows']] == names, out
        assert [r[1] for r in out['rows']] == names, out
        assert out['spare'] == '9 Yellow to 12 Aqua · spare (4)', out
        assert out['positions'] == [1, 2, 3, 4, 9, 10, 11, 12], out
        _section(pg, a)
        pg.locator(f'[data-lrd-field="fiber-strand-{a}-p1-0"]').click()
        pick = pg.locator(f'[data-lrd-field="fiber-strand-pick-{a}-p1-0"]')
        pick.wait_for()
        assert pick.evaluate("s => [...s.options].map(o => o.value)") == \
            ['1', '2', '3', '4', '9', '10', '11', '12']
        pg.evaluate("() => { document.activeElement && document.activeElement.blur(); }")
        pg.evaluate("() => window.app.renderHardwareDock()")
        pg.locator(f'[data-lrd-field="fiber-edit-{a}-p1"]').click()
        pg.locator(f'[data-lrd-field="fiber-strand-name-{mtp}-12"]').wait_for()
        fields = pg.evaluate("""(id) => [...document.querySelectorAll(
            `[data-lrd-field^="fiber-strand-name-${id}-"]`)].map(f => f.dataset.lrdField.split('-').pop())""", mtp)
        assert fields == ['1', '2', '3', '4', '9', '10', '11', '12'], fields
        pg.evaluate("() => { window.app._fiberEdit = null; window.app.renderHardwareDock(); }")
    finally:
        _set(pg, ids, strands=24, labels='numbers')
    assert ids['errors'] == []


def test_a_full_8_fiber_mtp_is_marked_full(page):
    """With every one of its eight strands taken - XD A 1-2, XD B 3-4, XD
    C 9-10, XD D 11-12 - another link's cable list shows the MTP as full
    and cannot pick it. Before Base-8 it counted 5-8 as free."""
    pg, ids = page
    sx, xds, mtp = ids['sx'], ids['xds'], ids['mtp']
    _set(pg, ids, strands=8, polarity='A')
    put = """async ([url, body]) => { const r = await fetch(url, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        await window.app.refreshProcessors(); window.app.renderHardwareDock(); return r.status; }"""
    try:
        for box in xds[2:]:
            assert pg.evaluate(put, [f'/api/processors/{sx}/cvts/{box}/fiber-links/p1', {'cable': mtp}]) == 200
        assert pg.evaluate(put, [f'/api/processors/{sx}', {'backupUnit': {'name': 'WALL SR BU'}}]) == 200
        _section(pg, xds[0])
        sel = pg.locator(f'[data-lrd-field="fiber-link-cable-{xds[0]}-b1"]')
        sel.wait_for()
        opt = sel.evaluate("""(s, id) => { const o = [...s.options].find(x => x.value === id);
                                            return o ? [o.textContent, o.disabled] : null; }""", mtp)
        assert opt and opt[0].endswith('· full') and opt[1] is True, opt
    finally:
        pg.evaluate(put, [f'/api/processors/{sx}', {'backupUnit': None}])
        for box in xds[2:]:
            pg.evaluate(put, [f'/api/processors/{sx}/cvts/{box}/fiber-links/p1', {'cable': None}])
        _set(pg, ids, strands=24)
    assert ids['errors'] == []


def test_the_pull_sheet_says_the_polarity_and_splits_by_it(page):
    """Owner, 2026-11-18: an MTP's pull row reads "MTP 24 Type A" with its
    length, and a Type A and a Type B of the same length are two rows with
    their own counts; two of one polarity are one row of 2. An edit saved
    on the old "MTP 24" row answers to the one MTP row of that length, and
    to neither where there are two."""
    pg, ids = page
    sx, xds, mtp = ids['sx'], ids['xds'], ids['mtp']
    _set(pg, ids, strands=24, polarity='A')
    made = pg.evaluate("""async ([box]) => {
        const r = await fetch('/api/fiber-cables', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({kind: 'mtp', strands: 24, ft: 300, polarity: 'B', link: {boxId: box, key: 'p1'}})});
        const st = await r.json();
        await window.app.refreshProcessors();
        return st.fiberCables[st.fiberCables.length - 1].id;
    }""", [xds[2]])
    rows = """() => window.app.buildPullSheet().totals.filter(r => r.type.startsWith('MTP'))
        .map(r => [r.type, r.length, r.qty])"""
    try:
        assert sorted(pg.evaluate(rows)) == [['MTP 24 Type A', "300'", 1], ['MTP 24 Type B', "300'", 1]]
        resolve = """(live) => window.app._pullResolveEditKey("MTP 24|300'", new Set(live))"""
        assert pg.evaluate(resolve, ["MTP 24 Type A|300'"]) == "MTP 24 Type A|300'"
        assert pg.evaluate(resolve, ["MTP 24 Type A|300'", "MTP 24 Type B|300'"]) == "MTP 24|300'"
        pg.evaluate(SET_JS, [made, {'polarity': 'A'}])
        assert pg.evaluate(rows) == [['MTP 24 Type A', "300'", 2]]
    finally:
        pg.evaluate("""async ([sx, box]) => {
            await fetch(`/api/processors/${sx}/cvts/${box}/fiber-links/p1`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({cable: null})});
            await window.app.refreshProcessors();
        }""", [sx, xds[2]])
    assert ids['errors'] == []
