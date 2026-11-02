"""Fiber extensions at the box end of a TAC or MTP link.

The owner, 2026-11-02: "MTP cant run direct to X1 for example it would need
an extension beyond that so being able to add a fiber extension off of it
would be nice same goes for Tac cable". His answers:

  - the extension sits at the BOX end only, between the TAC's or MTP's end
    and the box's port; the processor end is unchanged;
  - it records a kind (a fan-out or a duplex patch), the connector at each
    end (the fiber connector list, or typed; the trunk end starts as the
    trunk's own) and a length;
  - it is set per BOX LINK: each box's link off a shared trunk has its own
    or none, and a backup link can have its own;
  - it prints on the pull sheet (identical ones grouped with a count), on
    the box cable sheet's Fiber row, and in the binder's Fiber connections
    (at the breakout end) and strand map; no map cable tag;
  - it is optional, and a link without one behaves exactly as before.

Synthetic shows only: an SX40 whose XD A and XD B share one MTP 12, only
XD A's X1 extended; a NovaStar H9 with a CVT10 on a TAC with an extension.

Run locally (each session takes its own free port):
    python -m pytest tests/test_fiber_extensions.py -v --browser chromium
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402
from conftest import settled  # noqa: E402

H4 = 'novastar-card-h-4xfiber'


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


def _sx40(client):
    """An SX40 and its four XDs (trunks A-D), ids in trunk order."""
    st = _ok(client.post('/api/processors', json={'deviceId': 'brompton-sx40'}), 201)
    proc = st['processors'][-1]
    return proc['id'], [b['id'] for b in proc['slots'][0]['card']['cvts']]


def _h9_cvt10(client):
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}), 201)
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': H4}))
    cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']['id']
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': 'novastar-cvt10'}), 201)
    card = next(p for p in st['processors'] if p['id'] == pid)['slots'][0]['card']
    return pid, card['cvts'][0]['id']


def _new_cable(client, kind, link=None, **kw):
    body = dict(kind=kind, **kw)
    if link:
        body['link'] = link
    st = _ok(client.post('/api/fiber-cables', json=body), 201)
    return st['fiberCables'][-1]


def _link(client, pid, box, key, body):
    return client.put(f'/api/processors/{pid}/cvts/{box}/fiber-links/{key}', json=body)


def _raw_box(client, box_id):
    for proc in client.get('/api/processors').get_json()['processors']:
        for slot in proc['slots']:
            for box in (slot.get('card') or {}).get('cvts') or []:
                if box['id'] == box_id:
                    return box
    return None


def _links(client, box_id):
    return (_raw_box(client, box_id) or {}).get('fiberLinks')


def _shared_mtp(client):
    """The SX40 show: MTP A (12, 300') on XD A's X1 (1-2) and XD B's X1
    (3-4); only XD A's X1 has an extension - a fan-out to LC duplex, 10'."""
    pid, xds = _sx40(client)
    mtp = _new_cable(client, 'mtp', strands=12, ft=300, link={'boxId': xds[0], 'key': 'p1'})
    _ok(_link(client, pid, xds[1], 'p1', {'cable': mtp['id']}))
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {}}))
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'boxEnd': 'LC duplex', 'ft': 10}}))
    return pid, xds, mtp


# ── the store, through the Flask client ──────────────────────────────────

def test_an_extension_is_per_link_off_a_shared_mtp(client):
    """+ Extension on XD A's X1 starts as a fan-out (an MTP's first pick)
    with its trunk end left to follow the MTP; the keys sent change it.
    XD B's X1, on the same MTP, stores nothing new at all."""
    pid, xds = _sx40(client)
    mtp = _new_cable(client, 'mtp', strands=12, ft=300, link={'boxId': xds[0], 'key': 'p1'})
    _ok(_link(client, pid, xds[1], 'p1', {'cable': mtp['id']}))
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {}}))
    assert _links(client, xds[0]) == {'p1': {'cable': mtp['id'], 'strands': [1, 2],
                                             'extension': {'kind': 'fanout'}}}
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'boxEnd': ' LC duplex ', 'ft': 10}}))
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'trunkEnd': 'MTP / MPO'}}))
    assert _links(client, xds[0])['p1']['extension'] == {
        'kind': 'fanout', 'trunkEnd': 'MTP / MPO', 'boxEnd': 'LC duplex', 'ft': 10}
    # a blank end goes back to following the trunk; a blank length is none
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'trunkEnd': '', 'ft': ''}}))
    assert _links(client, xds[0])['p1']['extension'] == {'kind': 'fanout', 'boxEnd': 'LC duplex'}
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'kind': 'patch', 'ft': 12.5}}))
    assert _links(client, xds[0])['p1']['extension'] == {'kind': 'patch', 'boxEnd': 'LC duplex', 'ft': 12.5}
    # the other box's link off the same MTP is exactly as before
    assert _links(client, xds[1]) == {'p1': {'cable': mtp['id'], 'strands': [3, 4]}}
    # the resolved boxes carry it for every reader
    st = client.get('/api/processors').get_json()
    res = next(b for p in st['resolved'] if p['id'] == pid
               for b in p['slots'][0]['card']['cvts'] if b['id'] == xds[0])
    assert res['fiberLinks']['p1']['extension']['kind'] == 'patch'


def test_a_tac_starts_as_a_duplex_patch_and_a_backup_link_has_its_own(client):
    """A CVT10 on a TAC: the first pick is a duplex patch. On the SX40 with
    its backup unit, XD A's X2 takes its own extension, apart from X1's."""
    pid, cvt = _h9_cvt10(client)
    tac = _new_cable(client, 'tac', strands=12, ft=500, connector='ST',
                     link={'boxId': cvt, 'key': 'p1'})
    _ok(_link(client, pid, cvt, 'p1', {'extension': {'boxEnd': 'LC duplex', 'ft': 10}}))
    assert _links(client, cvt)['p1'] == {'cable': tac['id'], 'strands': [1, 2],
                                         'extension': {'kind': 'patch', 'boxEnd': 'LC duplex', 'ft': 10}}
    sx, xds, mtp = _shared_mtp(client)
    _ok(client.put(f'/api/processors/{sx}', json={'backupUnit': {'name': 'SX BU'}}))
    _ok(_link(client, sx, xds[0], 'b1', {'cable': mtp['id']}))
    assert 'extension' not in _links(client, xds[0])['b1']
    _ok(_link(client, sx, xds[0], 'b1', {'extension': {'kind': 'patch', 'ft': 6}}))
    links = _links(client, xds[0])
    assert links['b1']['extension'] == {'kind': 'patch', 'ft': 6}
    assert links['p1']['extension'] == {'kind': 'fanout', 'boxEnd': 'LC duplex', 'ft': 10}


def test_the_refusals_say_why_and_store_nothing(client):
    pid, xds, mtp = _shared_mtp(client)
    before = copy.deepcopy(_links(client, xds[0]))
    assert 'kind must be fanout or patch' in _refused(
        _link(client, pid, xds[0], 'p1', {'extension': {'kind': 'harness'}}))
    assert 'ft must be a number of feet' in _refused(
        _link(client, pid, xds[0], 'p1', {'extension': {'ft': 'long'}}))
    assert '0 or more' in _refused(_link(client, pid, xds[0], 'p1', {'extension': {'ft': -3}}))
    assert 'boxEnd must be text' in _refused(
        _link(client, pid, xds[0], 'p1', {'extension': {'boxEnd': 5}}))
    assert 'extension must be' in _refused(_link(client, pid, xds[0], 'p1', {'extension': 'yes'}))
    assert _links(client, xds[0]) == before
    # a link with no cable has nothing to extend
    why = _refused(_link(client, pid, xds[2], 'p1', {'extension': {}}))
    assert 'XD C X1 has no TAC or MTP to extend' in why, why
    # an opticalCON is not extended
    _new_cable(client, 'opticalcon-duo', link={'boxId': xds[2], 'key': 'p1'})
    why = _refused(_link(client, pid, xds[2], 'p1', {'extension': {}}))
    assert 'is on an opticalCON' in why, why
    assert 'extension' not in _links(client, xds[2])['p1']


def test_remove_is_one_request_and_the_link_stays(client):
    pid, xds, mtp = _shared_mtp(client)
    _ok(_link(client, pid, xds[0], 'p1', {'extension': None}))
    assert _links(client, xds[0]) == {'p1': {'cable': mtp['id'], 'strands': [1, 2]}}
    # removing one that is not there is harmless
    _ok(_link(client, pid, xds[0], 'p1', {'extension': None}))
    assert _links(client, xds[0]) == {'p1': {'cable': mtp['id'], 'strands': [1, 2]}}


def test_moving_strands_or_trunk_keeps_it_and_opticalcon_or_copper_drops_it(client):
    """The extension is the link's patch at the box: new strands or another
    TAC/MTP keep it; an opticalCON or copper on the link drops it."""
    pid, xds, mtp = _shared_mtp(client)
    ext = _links(client, xds[0])['p1']['extension']
    _ok(_link(client, pid, xds[0], 'p1', {'cable': mtp['id'], 'strands': [7, 8]}))
    assert _links(client, xds[0])['p1'] == {'cable': mtp['id'], 'strands': [7, 8], 'extension': ext}
    tac = _new_cable(client, 'tac', strands=12)
    _ok(_link(client, pid, xds[0], 'p1', {'cable': tac['id']}))
    assert _links(client, xds[0])['p1']['extension'] == ext
    duo = _new_cable(client, 'opticalcon-duo')
    _ok(_link(client, pid, xds[0], 'p1', {'cable': duo['id']}))
    assert 'extension' not in _links(client, xds[0])['p1']
    _ok(_link(client, pid, xds[0], 'p1', {'cable': mtp['id']}))
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {}}))
    _ok(_link(client, pid, xds[0], 'p1', {'copper': 'Cat6A', 'ft': 50}))
    assert _links(client, xds[0])['p1'] == {'copper': 'Cat6A', 'ft': 50}


def test_the_delete_cascade(client):
    """Clearing the link, deleting the box, or the MTP going with its last
    link each takes the extension with it."""
    pid, xds, mtp = _shared_mtp(client)
    _ok(_link(client, pid, xds[0], 'p1', {'cable': None}))
    assert _links(client, xds[0]) is None
    # the MTP's last link goes: the MTP goes, nothing of it is left
    _ok(_link(client, pid, xds[0], 'p1', {'cable': mtp['id']}))
    assert 'extension' not in _links(client, xds[0])['p1']
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'ft': 10}}))
    _ok(_link(client, pid, xds[1], 'p1', {'cable': None}))
    _ok(_link(client, pid, xds[0], 'p1', {'cable': None}))
    assert 'fiberCables' not in client.get('/api/project').get_json()
    # the box goes: its links and their extensions with it
    pid, xds, mtp = _shared_mtp(client)
    _ok(client.delete(f'/api/processors/{pid}/cvts/{xds[0]}'))
    assert _raw_box(client, xds[0]) is None
    proj = client.get('/api/project').get_json()
    assert 'extension' not in str(proj['processors']), proj['processors']


def test_save_load_and_undo_keep_it(client):
    """The undo snapshot is the whole project PUT back, and a saved file is
    the same project POSTed to the load funnel: the extension rides both."""
    pid, xds, mtp = _shared_mtp(client)
    want = copy.deepcopy(_links(client, xds[0]))
    snapshot = copy.deepcopy(client.get('/api/project').get_json())
    _ok(_link(client, pid, xds[0], 'p1', {'extension': None}))
    assert 'extension' not in _links(client, xds[0])['p1']
    snapshot.pop('next_processor_seq', None)
    _ok(client.put('/api/project', json=snapshot))
    assert _links(client, xds[0]) == want
    saved = copy.deepcopy(client.get('/api/project').get_json())
    _ok(_link(client, pid, xds[0], 'p1', {'cable': None}))
    _ok(client.post('/api/project', json=saved))
    assert _links(client, xds[0]) == want
    assert _links(client, xds[1]) == {'p1': {'cable': mtp['id'], 'strands': [3, 4]}}


def test_an_old_show_loads_unchanged(client):
    """A show from before extensions - links of {cable, strands} - passes
    the load funnel byte for byte; a stored extension that cannot be read
    drops only itself, and one on an opticalCON goes."""
    pid, xds = _sx40(client)
    mtp = _new_cable(client, 'mtp', strands=12, ft=300, link={'boxId': xds[0], 'key': 'p1'})
    _ok(_link(client, pid, xds[1], 'p1', {'cable': mtp['id']}))
    old = copy.deepcopy(client.get('/api/project').get_json())
    assert 'extension' not in str(old['processors'])
    project = copy.deepcopy(old)
    assert catalog.settle_fiber(project) is False
    assert project == old
    _ok(client.post('/api/project', json=old))
    again = client.get('/api/project').get_json()
    assert again['processors'] == old['processors']
    assert again['fiberCables'] == old['fiberCables']
    # unreadable: the link stays as it was
    raw = copy.deepcopy(old)
    box = next(b for b in raw['processors'][-1]['slots'][0]['card']['cvts'] if b['id'] == xds[0])
    box['fiberLinks']['p1']['extension'] = {'kind': 'harness', 'ft': 10}
    assert catalog.settle_fiber(raw) is True
    assert box['fiberLinks']['p1'] == {'cable': mtp['id'], 'strands': [1, 2]}
    # on an opticalCON: dropped, the link kept
    raw = copy.deepcopy(old)
    raw['fiberCables'][0]['kind'] = 'opticalcon-quad'
    box = next(b for b in raw['processors'][-1]['slots'][0]['card']['cvts'] if b['id'] == xds[0])
    box['fiberLinks']['p1']['extension'] = {'kind': 'patch'}
    catalog.settle_fiber(raw)
    assert box['fiberLinks']['p1'] == {'cable': mtp['id'], 'strands': [1, 2]}


def test_the_shape_reader():
    assert catalog._fiber_extension({'kind': 'fanout', 'trunkEnd': '  ', 'boxEnd': ' LC ',
                                     'ft': 0, 'junk': 1}) == {'kind': 'fanout', 'boxEnd': 'LC'}
    assert catalog._fiber_extension({'kind': 'patch', 'ft': '25'}) == {'kind': 'patch', 'ft': 25}
    assert catalog._fiber_extension({'ft': 10}) is None
    assert catalog._fiber_extension('fanout') is None
    assert catalog.merge_fiber_extension(None, {}, {'kind': 'mtp'}) == {'kind': 'fanout'}
    assert catalog.merge_fiber_extension(None, {}, {'kind': 'tac'}) == {'kind': 'patch'}


# ── the browser: the sheet, the pull sheet, the binder ───────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# WALL: one screen, so the pull sheet has a position.
# SX: an SX40 - MTP A (12, 300') on XD A's X1 (1-2, a fan-out to LC
# duplex, 10') and XD B's X1 (3-4, no extension); an opticalCON DUO on XD
# C's X1.
# NOVA: an H9 with an H_4xfiber - a CVT10 on TAC A (12, 500', ST), its
# OPT 1 extended with a duplex patch to LC duplex, 10'.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'WALL', columns: 4, rows: 4,
                                       cabinet_width: 200, cabinet_height: 200});
    const last = (st) => st.processors[st.processors.length - 1];
    const cable = (st) => st.fiberCables[st.fiberCables.length - 1];
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40', name: 'SX'});
    const sx = last(st).id;
    const xds = last(st).slots[0].card.cvts.map(b => b.id);
    st = await j('POST', '/api/fiber-cables', {kind: 'mtp', strands: 12, ft: 300,
                                               link: {boxId: xds[0], key: 'p1'}});
    const mtp = cable(st);
    await j('PUT', `/api/processors/${sx}/cvts/${xds[1]}/fiber-links/p1`, {cable: mtp.id});
    await j('PUT', `/api/processors/${sx}/cvts/${xds[0]}/fiber-links/p1`,
            {extension: {boxEnd: 'LC duplex', ft: 10}});
    await j('POST', '/api/fiber-cables', {kind: 'opticalcon-duo', link: {boxId: xds[2], key: 'p1'}});
    st = await j('POST', '/api/processors', {deviceId: 'novastar-h9', name: 'NOVA'});
    const nova = last(st).id;
    st = await j('PUT', `/api/processors/${nova}/slots/0`, {deviceId: 'novastar-card-h-4xfiber'});
    const novaCard = st.processors.find(p => p.id === nova).slots[0].card.id;
    st = await j('POST', `/api/processors/${nova}/cards/${novaCard}/cvts`, {deviceId: 'novastar-cvt10'});
    const cvt = st.processors.find(p => p.id === nova).slots[0].card.cvts[0].id;
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 12, ft: 500, connector: 'ST',
                                               link: {boxId: cvt, key: 'p1'}});
    const tac = cable(st);
    await j('PUT', `/api/processors/${nova}/cvts/${cvt}/fiber-links/p1`,
            {extension: {boxEnd: 'LC duplex', ft: 10}});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('fiber_extensions_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Fiber Extensions Seed');
    return {sx, xds, nova, cvt, mtp, tac};
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

# The box's Fiber section as it reads: each link row's buttons, and each
# extension line's fields.
SECTION_JS = """(boxId) => {
    const sec = document.querySelector(`[data-lrd-fiber-row="${boxId}"]`);
    if (!sec) return null;
    return {
        rows: [...sec.querySelectorAll('.hw-dock-fiber-link')].map(r => ({
            link: r.dataset.lrdFiberLink,
            buttons: [...r.querySelectorAll('button.hw-dock-btn')].map(b => b.textContent),
            nextIsExt: !!(r.nextElementSibling && r.nextElementSibling.classList.contains('hw-dock-fiber-ext')),
        })),
        exts: [...sec.querySelectorAll('.hw-dock-fiber-ext')].map(e => ({
            link: e.dataset.lrdFiberExt,
            cap: e.querySelector('.hw-dock-fiber-ext-cap').textContent,
            kind: e.querySelector('select').value,
            kinds: [...e.querySelector('select').options].map(o => o.textContent),
            ends: [...e.querySelectorAll('.hw-dock-fiber-ext-end')].map(f => f.value),
            offered: [...e.querySelectorAll('datalist option')].map(o => o.value),
            ft: e.querySelector('.hw-dock-cable-ft').value,
            buttons: [...e.querySelectorAll('button')].map(b => b.textContent),
        })),
    };
}"""

LIST_JS = """() => {
    const app = window.app;
    const out = JSON.parse(JSON.stringify(app.buildPullList()));
    const rows = (list) => list.map(r => [r.type, r.length, r.qty, r.label, r.notes]);
    return { totals: rows(out.totals),
             hardware: out.hardware.filter(h => h.kind === 'processor').map(h => [h.id, rows(h.rows)]) };
}"""

PUT_JS = """async ([url, body]) => {
    const r = await fetch(url, {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify(body)});
    const st = await r.json();
    await window.app.refreshProcessors();
    return st;
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
    settled(pg, lambda: pg.evaluate(
        "(id) => !!(window.app._processorsResolved || []).find(p => p.id === id)", ids['nova']),
        bool, 5000)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _served_links(pg, box_id):
    return pg.evaluate("""async (id) => {
        const st = await (await fetch('/api/processors')).json();
        for (const p of st.processors) for (const s of p.slots)
            for (const b of ((s.card || {}).cvts || [])) if (b.id === id) return b.fiberLinks || null;
        return null;
    }""", box_id)


def _wait_links(pg, box_id, ok, timeout=8000):
    return settled(pg, lambda: _served_links(pg, box_id), ok, timeout)


def _section(pg, box_id):
    assert pg.evaluate(OPEN_SHEET_JS, box_id), f'the cable sheet of {box_id} did not open'
    pg.wait_for_timeout(200)
    return pg.evaluate(SECTION_JS, box_id)


def _history(pg):
    return pg.evaluate('() => [window.app.historyIndex, '
                       '(window.app.history[window.app.historyIndex] || {}).action]')


def test_the_box_sheet_shows_the_extension_under_its_link(page):
    """XD A's ≡ sheet: its X1 row (on MTP A) is followed by the extension
    line - "X1 extension", Fan-out, the trunk end following the MTP (MTP /
    MPO), LC duplex, 10, Remove - its ends offered from the fiber connector
    list. No + Extension on a link that has one; XD C's opticalCON link
    offers none."""
    pg, ids = page
    sec = _section(pg, ids['xds'][0])
    assert sec['rows'][0]['link'] == f"{ids['xds'][0]}:p1"
    assert '+ Extension' not in sec['rows'][0]['buttons'], sec
    assert sec['rows'][0]['nextIsExt'], sec
    assert sec['exts'] == [{
        'link': f"{ids['xds'][0]}:p1", 'cap': 'X1 extension', 'kind': 'fanout',
        'kinds': ['Fan-out', 'Duplex patch'], 'ends': ['MTP / MPO', 'LC duplex'],
        'offered': ['ST', 'LC duplex', 'opticalCON DUO', 'opticalCON QUAD', 'MTP / MPO'],
        'ft': '10', 'buttons': ['Remove']}], sec
    sec = _section(pg, ids['xds'][2])
    assert all('+ Extension' not in r['buttons'] for r in sec['rows']), sec
    assert sec['exts'] == []
    # the CVT10's TAC: ST at the trunk end, a duplex patch
    sec = _section(pg, ids['cvt'])
    assert [(e['kind'], e['ends'], e['ft']) for e in sec['exts']] == [('patch', ['ST', 'LC duplex'], '10')], sec
    assert ids['errors'] == []


def test_plus_extension_edits_and_remove_are_one_step_each(page):
    """XD B's X1 shares MTP A with no extension: + Extension adds one in
    ONE history entry; its box end and length are typed; Remove takes it
    off in one click and one entry; undo brings it back. It is left as XD
    A's twin for the pull sheet test."""
    pg, ids = page
    b = ids['xds'][1]
    sec = _section(pg, b)
    assert '+ Extension' in sec['rows'][0]['buttons'], sec
    assert sec['exts'] == []
    index, _ = _history(pg)
    pg.locator(f'[data-lrd-field="fiber-ext-add-{b}-p1"]').click()
    links = _wait_links(pg, b, lambda v: v and 'extension' in v['p1'])
    assert links['p1'] == {'cable': ids['mtp']['id'], 'strands': [3, 4], 'extension': {'kind': 'fanout'}}
    assert settled(pg, lambda: _history(pg), lambda h: h[0] == index + 1) == [index + 1, 'Add Fiber Extension']
    box_end = pg.locator(f'[data-lrd-field="fiber-ext-box-{b}-p1"]')
    box_end.wait_for()
    box_end.fill('LC duplex')
    box_end.press('Enter')
    _wait_links(pg, b, lambda v: v and v['p1'].get('extension', {}).get('boxEnd') == 'LC duplex')
    ft = pg.locator(f'[data-lrd-field="fiber-ext-ft-{b}-p1"]')
    ft.fill('10')
    ft.press('Enter')
    links = _wait_links(pg, b, lambda v: v and v['p1'].get('extension', {}).get('ft') == 10)
    assert links['p1']['extension'] == {'kind': 'fanout', 'boxEnd': 'LC duplex', 'ft': 10}
    assert settled(pg, lambda: _history(pg), lambda h: h[0] == index + 3) == [index + 3, 'Set Fiber Extension']
    # typing the trunk's own connector stores nothing: it follows the MTP
    trunk = pg.locator(f'[data-lrd-field="fiber-ext-trunk-{b}-p1"]')
    assert trunk.input_value() == 'MTP / MPO'
    # Remove: one click, one entry, the link as it was
    pg.locator(f'[data-lrd-field="fiber-ext-remove-{b}-p1"]').click()
    links = _wait_links(pg, b, lambda v: v and 'extension' not in v['p1'])
    assert links['p1'] == {'cable': ids['mtp']['id'], 'strands': [3, 4]}
    assert settled(pg, lambda: _history(pg), lambda h: h[0] == index + 4) == [index + 4, 'Remove Fiber Extension']
    pg.evaluate('() => window.app.undo()')
    links = _wait_links(pg, b, lambda v: v and 'extension' in v['p1'])
    assert links['p1']['extension'] == {'kind': 'fanout', 'boxEnd': 'LC duplex', 'ft': 10}
    pg.evaluate('() => window.app.refreshProcessors()')
    pg.wait_for_timeout(300)
    assert ids['errors'] == []


def test_the_pull_sheet_groups_identical_extensions(page):
    """XD A's and XD B's extensions - a fan-out, MTP / MPO to LC duplex, 10'
    - are ONE row of 2; MTP A is still one row. Made 15' on XD B, they are
    two rows; with XD B's removed, XD A's alone is a row of 1. The NOVA
    CVT10's duplex patch is its own row on NOVA's list."""
    pg, ids = page
    out = pg.evaluate(LIST_JS)
    fan = [r for r in out['totals'] if r[0].startswith('Fan-out')]
    assert [r[:3] for r in fan] == [['Fan-out · MTP / MPO to LC duplex', "10'", 2]], out['totals']
    assert 'ext · MTP A' in fan[0][4], fan
    assert [r[:3] for r in out['totals'] if r[0].startswith('MTP')] == [['MTP 12', "300'", 1]], out['totals']
    patch = [r for r in out['totals'] if r[0].startswith('Duplex patch')]
    assert patch == [['Duplex patch · ST to LC duplex', "10'", 1, 'CVT10 A (OPT 1)', 'ext · TAC A']], out['totals']
    nova = dict(out['hardware'])[ids['nova']]
    assert ['Duplex patch · ST to LC duplex', "10'", 1, 'CVT10 A (OPT 1)', 'ext · TAC A'] in nova, nova
    sx = dict(out['hardware'])[ids['sx']]
    assert [r[:3] for r in sx if r[0].startswith('Fan-out')] == [['Fan-out · MTP / MPO to LC duplex', "10'", 2]], sx
    b = ids['xds'][1]
    pg.evaluate(PUT_JS, [f"/api/processors/{ids['sx']}/cvts/{b}/fiber-links/p1", {'extension': {'ft': 15}}])
    out = pg.evaluate(LIST_JS)
    fan = sorted(r[:3] for r in out['totals'] if r[0].startswith('Fan-out'))
    assert fan == [['Fan-out · MTP / MPO to LC duplex', "10'", 1],
                   ['Fan-out · MTP / MPO to LC duplex', "15'", 1]], out['totals']
    pg.evaluate(PUT_JS, [f"/api/processors/{ids['sx']}/cvts/{b}/fiber-links/p1", {'extension': None}])
    out = pg.evaluate(LIST_JS)
    fan = [r for r in out['totals'] if r[0].startswith('Fan-out')]
    assert [r[:4] for r in fan] == [['Fan-out · MTP / MPO to LC duplex', "10'", 1, 'XD A (X1)']], out['totals']
    assert ids['errors'] == []


def test_the_binder_fiber_connections_shows_it_at_the_breakout(page):
    """SX: trunk A's row ends AT THE BREAKOUT with "ext Fan-out 10'" and
    "MTP / MPO to LC duplex" after the MTP's "crosses inside"; trunk B's
    row, on the same MTP with no extension, is exactly as before. NOVA's
    OPT 1 ends the same way after the TAC's flipped pair."""
    pg, ids = page
    rows = pg.evaluate("""(pid) => {
        const app = window.app;
        const proc = app._processorsResolved.find(p => p.id === pid);
        return app._bFiberConnectionRows(proc).map(r => r.cells);
    }""", ids['sx'])
    assert rows[0] == ['trunk A', 'MTP A (MTP 12)', '1 Blue · 2 Orange', 'X1 on XD A',
                       "1 Blue · 2 Orange · crosses inside · ext Fan-out 10' · MTP / MPO to LC duplex"], rows
    assert rows[1] == ['trunk B', 'MTP A', '3 Green · 4 Brown', 'X1 on XD B',
                       '3 Green · 4 Brown · crosses inside'], rows
    rows = pg.evaluate("""(pid) => {
        const app = window.app;
        const proc = app._processorsResolved.find(p => p.id === pid);
        return app._bFiberConnectionRows(proc).map(r => r.cells);
    }""", ids['nova'])
    assert rows[0] == ['OPT 1', 'TAC A (TAC 12 · ST)', '1 Blue · 2 Orange', 'OPT 1 on CVT10 A',
                       "2 Orange · 1 Blue · ext Duplex patch 10' · ST to LC duplex"], rows
    assert ids['errors'] == []


def test_the_strand_map_notes_it_beside_the_link(page):
    pg, ids = page
    maps = pg.evaluate("""(pid) => {
        const app = window.app;
        const proc = app._processorsResolved.find(p => p.id === pid);
        return app._bStrandMaps(proc).map(m => ({title: m.title, rows: m.rows.map(r => r.cells)}));
    }""", ids['sx'])
    mtp = next(m for m in maps if m['title'].startswith('Strand map · MTP A'))
    assert [r[1] for r in mtp['rows'][:5]] == [
        "XD A · X1 · ext Fan-out 10'", "XD A · X1 · ext Fan-out 10'", 'XD B · X1', 'XD B · X1', 'spare'], mtp
    maps = pg.evaluate("""(pid) => {
        const app = window.app;
        const proc = app._processorsResolved.find(p => p.id === pid);
        return app._bStrandMaps(proc).map(m => m.rows.map(r => r.cells[1]));
    }""", ids['nova'])
    assert maps[0][:3] == ["CVT10 A · OPT 1 · ext Duplex patch 10'"] * 2 + ['spare'], maps
    assert ids['errors'] == []


def test_the_text_helpers(page):
    """No length reads "no length"; an end left blank on a TAC with no ends
    names only the other; the one-line text the guide's note uses."""
    pg, _ids = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const tac = {kind: 'tac', strands: 12}, st = {kind: 'tac', strands: 12, connector: 'ST'};
        const mtp = {kind: 'mtp', strands: 12};
        return [
            app.fiberExtensionText({kind: 'patch'}, tac),
            app.fiberExtensionText({kind: 'patch', boxEnd: 'LC duplex', ft: 10}, tac),
            app.fiberExtensionText({kind: 'patch', ft: 10}, st),
            app.fiberExtensionText({kind: 'fanout', trunkEnd: 'MPO 12', boxEnd: 'LC duplex', ft: 6}, mtp),
            app.fiberExtensionType({kind: 'fanout', boxEnd: 'LC duplex'}, mtp),
        ];
    }""")
    assert out == ['Duplex patch · no length', "Duplex patch · to LC duplex · 10'",
                   "Duplex patch · from ST · 10'", "Fan-out · MPO 12 to LC duplex · 6'",
                   'Fan-out · MTP / MPO to LC duplex']
