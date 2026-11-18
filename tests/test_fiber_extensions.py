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
    (3-4); only XD A's X1 has an extension - a fan-out to LC duplex, 10'
    (picked: an MTP's own first pick is a duplex patch)."""
    pid, xds = _sx40(client)
    mtp = _new_cable(client, 'mtp', strands=12, ft=300, link={'boxId': xds[0], 'key': 'p1'})
    _ok(_link(client, pid, xds[1], 'p1', {'cable': mtp['id']}))
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {}}))
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'kind': 'fanout', 'boxEnd': 'LC duplex',
                                                        'ft': 10}}))
    return pid, xds, mtp


# ── the store, through the Flask client ──────────────────────────────────

def test_an_extension_is_per_link_off_a_shared_mtp(client):
    """+ Extension on XD A's X1 starts as a duplex patch (an MTP's first
    pick, owner 2026-11-02: "for mtp patch should default") with no box end
    and its trunk end left to follow the MTP; the keys sent change it.
    XD B's X1, on the same MTP, stores nothing new at all."""
    pid, xds = _sx40(client)
    mtp = _new_cable(client, 'mtp', strands=12, ft=300, link={'boxId': xds[0], 'key': 'p1'})
    _ok(_link(client, pid, xds[1], 'p1', {'cable': mtp['id']}))
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {}}))
    assert _links(client, xds[0]) == {'p1': {'cable': mtp['id'], 'strands': [1, 2],
                                             'extension': {'kind': 'patch'}}}
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'boxEnd': ' LC duplex ', 'ft': 10}}))
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'trunkEnd': 'MTP / MPO'}}))
    assert _links(client, xds[0])['p1']['extension'] == {
        'kind': 'patch', 'trunkEnd': 'MTP / MPO', 'boxEnd': 'LC duplex', 'ft': 10}
    # a blank end goes back to following the trunk; a blank length is none
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'trunkEnd': '', 'ft': ''}}))
    assert _links(client, xds[0])['p1']['extension'] == {'kind': 'patch', 'boxEnd': 'LC duplex'}
    _ok(_link(client, pid, xds[0], 'p1', {'extension': {'kind': 'fanout', 'ft': 12.5}}))
    assert _links(client, xds[0])['p1']['extension'] == {'kind': 'fanout', 'boxEnd': 'LC duplex', 'ft': 12.5}
    # the other box's link off the same MTP is exactly as before
    assert _links(client, xds[1]) == {'p1': {'cable': mtp['id'], 'strands': [3, 4]}}
    # the resolved boxes carry it for every reader
    st = client.get('/api/processors').get_json()
    res = next(b for p in st['resolved'] if p['id'] == pid
               for b in p['slots'][0]['card']['cvts'] if b['id'] == xds[0])
    assert res['fiberLinks']['p1']['extension']['kind'] == 'fanout'


def test_a_tac_starts_as_a_fan_out_to_lc_duplex_and_a_backup_link_has_its_own(client):
    """A CVT10 on a TAC: the first pick is a fan-out to LC duplex (owner
    2026-11-02: "For tac fan out should be default"), whatever the TAC's
    own ends - an ST TAC's reads ST to LC duplex, an LC duplex TAC's LC
    duplex at both ends. On the SX40 with its backup unit, XD A's X2 takes
    its own extension, apart from X1's."""
    pid, cvt = _h9_cvt10(client)
    tac = _new_cable(client, 'tac', strands=12, ft=500, connector='ST',
                     link={'boxId': cvt, 'key': 'p1'})
    _ok(_link(client, pid, cvt, 'p1', {'extension': {}}))
    assert _links(client, cvt)['p1'] == {'cable': tac['id'], 'strands': [1, 2],
                                         'extension': {'kind': 'fanout', 'boxEnd': 'LC duplex'}}
    _ok(_link(client, pid, cvt, 'p1', {'extension': {'ft': 10}}))
    assert _links(client, cvt)['p1']['extension'] == {'kind': 'fanout', 'boxEnd': 'LC duplex', 'ft': 10}
    # an LC duplex TAC starts the same way
    lc_pid, lc_cvt = _h9_cvt10(client)
    _new_cable(client, 'tac', strands=12, ft=500, connector='LC duplex',
               link={'boxId': lc_cvt, 'key': 'p1'})
    _ok(_link(client, lc_pid, lc_cvt, 'p1', {'extension': {}}))
    assert _links(client, lc_cvt)['p1']['extension'] == {'kind': 'fanout', 'boxEnd': 'LC duplex'}
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
    link = _links(client, xds[0])['p1']
    assert link == {'copper': 'Cat6A', 'ft': 50, 'name': link.get('name')}, link
    assert str(link['name']).startswith('Cat6A '), link


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
    # a new one: a duplex patch off an MTP, a fan-out to LC duplex off a TAC
    assert catalog.merge_fiber_extension(None, {}, {'kind': 'mtp'}) == {'kind': 'patch'}
    assert catalog.merge_fiber_extension(None, {}, {'kind': 'tac'}) == {
        'kind': 'fanout', 'boxEnd': 'LC duplex'}
    assert catalog.merge_fiber_extension(None, {}, {'kind': 'tac', 'connector': 'ST'}) == {
        'kind': 'fanout', 'boxEnd': 'LC duplex'}
    # the first pick is only a start: the keys sent win over it
    assert catalog.merge_fiber_extension(None, {'kind': 'patch', 'boxEnd': ''},
                                         {'kind': 'tac'}) == {'kind': 'patch'}


# ── the browser: the sheet, the pull sheet, the binder ───────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# WALL: one screen, so the pull sheet has a position.
# SX: an SX40 - MTP A (12, 300') on XD A's X1 (1-2, a duplex patch to LC
# duplex, 10') and XD B's X1 (3-4, no extension); an opticalCON DUO on XD
# C's X1.
# NOVA: an H9 with an H_4xfiber - a CVT10 on TAC A (12, 500', ST), its
# OPT 1 extended with a fan-out to LC duplex, 10'.
# Each kind is sent, not left to the first pick, so these tests read the
# same whatever a new extension starts as.
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
            {extension: {kind: 'patch', boxEnd: 'LC duplex', ft: 10}});
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
            {extension: {kind: 'fanout', boxEnd: 'LC duplex', ft: 10}});
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
            carets: e.querySelectorAll('.hw-dock-combo-caret').length,
            ft: e.querySelector('.hw-dock-cable-ft').value,
            buttons: [...e.querySelectorAll('button:not(.hw-dock-combo-caret)')].map(b => b.textContent),
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
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    # a processor with no screens is off the binder and the pull sheet
    # (owner, 2026-11-17): every processor here gets one
    from test_hidden_screen_binder import FEED_JS
    pg.evaluate(FEED_JS)
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
    line - "X1 extension", Duplex patch, the trunk end following the MTP
    (MTP / MPO), LC duplex, 10, Remove - each end with its dropdown caret. No + Extension on a link that has one; XD C's opticalCON link
    offers none."""
    pg, ids = page
    sec = _section(pg, ids['xds'][0])
    assert sec['rows'][0]['link'] == f"{ids['xds'][0]}:p1"
    assert '+ Extension' not in sec['rows'][0]['buttons'], sec
    assert sec['rows'][0]['nextIsExt'], sec
    assert sec['exts'] == [{
        'link': f"{ids['xds'][0]}:p1", 'cap': 'X1 extension', 'kind': 'patch',
        'kinds': ['Fan-out', 'Duplex patch'], 'ends': ['MTP / MPO', 'LC duplex'],
        'carets': 2,
        'ft': '10', 'buttons': ['Remove']}], sec
    sec = _section(pg, ids['xds'][2])
    assert all('+ Extension' not in r['buttons'] for r in sec['rows']), sec
    assert sec['exts'] == []
    # the CVT10's TAC: ST at the trunk end, a fan-out
    sec = _section(pg, ids['cvt'])
    assert [(e['kind'], e['ends'], e['ft']) for e in sec['exts']] == [('fanout', ['ST', 'LC duplex'], '10')], sec
    assert ids['errors'] == []


def test_plus_extension_edits_and_remove_are_one_step_each(page):
    """XD B's X1 shares MTP A with no extension: + Extension adds one -
    a duplex patch, an MTP's first pick - in ONE history entry; its box end
    and length are typed; Remove takes it
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
    assert links['p1'] == {'cable': ids['mtp']['id'], 'strands': [3, 4], 'extension': {'kind': 'patch'}}
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
    assert links['p1']['extension'] == {'kind': 'patch', 'boxEnd': 'LC duplex', 'ft': 10}
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
    assert links['p1']['extension'] == {'kind': 'patch', 'boxEnd': 'LC duplex', 'ft': 10}
    pg.evaluate('() => window.app.refreshProcessors()')
    pg.wait_for_timeout(300)
    assert ids['errors'] == []


def test_the_pull_sheet_groups_identical_extensions(page):
    """XD A's and XD B's extensions - a duplex patch, MTP / MPO to LC
    duplex, 10' - are ONE row of 2; MTP A is still one row. Made 15' on XD
    B, they are two rows; with XD B's removed, XD A's alone is a row of 1.
    The NOVA CVT10's fan-out is its own row on NOVA's list."""
    pg, ids = page
    out = pg.evaluate(LIST_JS)
    pat = [r for r in out['totals'] if r[0].startswith('Duplex patch')]
    assert [r[:3] for r in pat] == [['Duplex patch · MTP / MPO to LC duplex', "10'", 2]], out['totals']
    assert 'ext · MTP A' in pat[0][4], pat
    assert [r[:3] for r in out['totals'] if r[0].startswith('MTP')] == [['MTP 12', "300'", 1]], out['totals']
    fan = [r for r in out['totals'] if r[0].startswith('Fan-out')]
    assert fan == [['Fan-out · ST to LC duplex · Single mode', "10'", 1, 'CVT10-S A (OPT 1)',
                    'ext · TAC A']], out['totals']
    nova = dict(out['hardware'])[ids['nova']]
    assert ['Fan-out · ST to LC duplex · Single mode', "10'", 1, 'CVT10-S A (OPT 1)',
            'ext · TAC A'] in nova, nova
    sx = dict(out['hardware'])[ids['sx']]
    assert [r[:3] for r in sx if r[0].startswith('Duplex patch')] == [
        ['Duplex patch · MTP / MPO to LC duplex', "10'", 2]], sx
    b = ids['xds'][1]
    pg.evaluate(PUT_JS, [f"/api/processors/{ids['sx']}/cvts/{b}/fiber-links/p1", {'extension': {'ft': 15}}])
    out = pg.evaluate(LIST_JS)
    pat = sorted(r[:3] for r in out['totals'] if r[0].startswith('Duplex patch'))
    assert pat == [['Duplex patch · MTP / MPO to LC duplex', "10'", 1],
                   ['Duplex patch · MTP / MPO to LC duplex', "15'", 1]], out['totals']
    pg.evaluate(PUT_JS, [f"/api/processors/{ids['sx']}/cvts/{b}/fiber-links/p1", {'extension': None}])
    out = pg.evaluate(LIST_JS)
    pat = [r for r in out['totals'] if r[0].startswith('Duplex patch')]
    assert [r[:4] for r in pat] == [['Duplex patch · MTP / MPO to LC duplex', "10'", 1, 'XD A (X1)']], out['totals']
    assert ids['errors'] == []


def test_the_binder_fiber_connections_shows_it_at_the_breakout(page):
    """SX: trunk A's row ends AT THE BREAKOUT with "ext Duplex patch 10'" and
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
                       "1 Blue · 2 Orange · crosses inside · ext Duplex patch 10' · MTP / MPO to LC duplex"], rows
    assert rows[1] == ['trunk B', 'MTP A', '3 Green · 4 Brown', 'X1 on XD B',
                       '3 Green · 4 Brown · crosses inside'], rows
    rows = pg.evaluate("""(pid) => {
        const app = window.app;
        const proc = app._processorsResolved.find(p => p.id === pid);
        return app._bFiberConnectionRows(proc).map(r => r.cells);
    }""", ids['nova'])
    assert rows[0] == ['OPT 1', 'TAC A (TAC 12 · ST · Single mode)', '1 Blue · 2 Orange', 'OPT 1 on CVT10-S A',
                       "2 Orange · 1 Blue · ext Fan-out 10' · ST to LC duplex · Single mode"], rows
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
        "XD A · X1 · ext Duplex patch 10'", "XD A · X1 · ext Duplex patch 10'", 'XD B · X1', 'XD B · X1',
        'spare'], mtp
    maps = pg.evaluate("""(pid) => {
        const app = window.app;
        const proc = app._processorsResolved.find(p => p.id === pid);
        return app._bStrandMaps(proc).map(m => m.rows.map(r => r.cells[1]));
    }""", ids['nova'])
    assert maps[0][:3] == ["CVT10-S A · OPT 1 · ext Fan-out 10'"] * 2 + ['spare'], maps
    assert ids['errors'] == []


def test_the_text_helpers(page):
    """No length reads "no length"; an end left blank on a TAC with no ends
    names only the other; the one-line text the guide's note uses. A new
    extension's first pick reads LC duplex at both ends off an LC duplex
    TAC, ST to LC duplex off an ST one, and the MTP's own end off an MTP."""
    pg, _ids = page
    out = pg.evaluate("""() => {
        const app = window.app;
        const tac = {kind: 'tac', strands: 12}, st = {kind: 'tac', strands: 12, connector: 'ST'};
        const mtp = {kind: 'mtp', strands: 12};
        const lc = {kind: 'tac', strands: 12, connector: 'LC duplex'};
        const tacFirst = {kind: 'fanout', boxEnd: 'LC duplex'}, mtpFirst = {kind: 'patch'};
        return [
            app.fiberExtensionText({kind: 'patch'}, tac),
            app.fiberExtensionText({kind: 'patch', boxEnd: 'LC duplex', ft: 10}, tac),
            app.fiberExtensionText({kind: 'patch', ft: 10}, st),
            app.fiberExtensionText({kind: 'fanout', trunkEnd: 'MPO 12', boxEnd: 'LC duplex', ft: 6}, mtp),
            app.fiberExtensionType({kind: 'fanout', boxEnd: 'LC duplex'}, mtp),
            app.fiberExtensionText(tacFirst, lc),
            app.fiberExtensionText(tacFirst, st),
            app.fiberExtensionText(mtpFirst, mtp),
        ];
    }""")
    assert out == ['Duplex patch · no length', "Duplex patch · to LC duplex · 10'",
                   "Duplex patch · from ST · 10'", "Fan-out · MPO 12 to LC duplex · 6'",
                   'Fan-out · MTP / MPO to LC duplex',
                   'Fan-out · LC duplex to LC duplex · no length',
                   'Fan-out · ST to LC duplex · no length',
                   'Duplex patch · from MTP / MPO · no length']


# ── the ends read as dropdowns (owner, 2026-11-18) ───────────────────────
#
# "under fiber extensions where it says box end needs to be a drop down
# visibly. it already is one currently but doesnt look like it". Each end
# is a text box with a caret like the kind's select beside it; the caret,
# or a click in the empty field, opens the connector list; a pick commits
# in one request and one history entry; typing a connector of one's own
# still works; Esc closes the list and nothing else. These run last: they
# rewrite XD A's extension, which the tests above read.

CONNECTORS = ['ST', 'LC duplex', 'opticalCON DUO', 'opticalCON QUAD', 'MTP / MPO']

# Counts the page's writes to the boxes' fiber links.
COUNT_PUTS_JS = """() => {
    if (!window.__extPuts) {
        window.__extPuts = [];
        const was = window.fetch;
        window.fetch = function (url, opts) {
            if (opts && opts.method === 'PUT' && String(url).includes('/fiber-links/'))
                window.__extPuts.push(String(url));
            return was.apply(this, arguments);
        };
    }
    window.__extPuts.length = 0;
    return true;
}"""


def _menu(pg, key):
    return pg.locator(f'[data-lrd-combo-menu="{key}"]')


def _menu_items(pg, key):
    return pg.evaluate("""(key) => {
        const m = document.querySelector(`[data-lrd-combo-menu="${key}"]`);
        return m ? [...m.querySelectorAll('[role="option"]')].map(o => o.textContent) : null;
    }""", key)


def _puts(pg):
    return pg.evaluate('() => window.__extPuts.slice()')


def _focused(pg):
    return pg.evaluate('() => document.activeElement && document.activeElement.dataset.lrdField')


def _box_end(pg, box_id):
    links = _served_links(pg, box_id) or {}
    return (links.get('p1') or {}).get('extension', {}).get('boxEnd')


def test_each_end_shows_a_caret_and_the_caret_opens_the_list(page):
    """Both ends carry a visible caret at their right edge, drawn the same
    in every browser; no browser suggestion list rides the field. A click
    on the caret opens the five connectors beside the field, the stored
    one marked; a second click closes it."""
    pg, ids = page
    b = ids['xds'][0]
    _section(pg, b)
    for end in ('trunk', 'box'):
        key = f'fiber-ext-{end}-{b}-p1'
        caret = pg.locator(f'[data-lrd-combo-caret="{key}"]')
        assert caret.is_visible(), key
        look = pg.evaluate("""(key) => {
            const f = document.querySelector(`[data-lrd-field="${key}"]`);
            const c = document.querySelector(`[data-lrd-combo-caret="${key}"]`);
            const fr = f.getBoundingClientRect(), cr = c.getBoundingClientRect();
            return {list: f.hasAttribute('list'), img: getComputedStyle(c).backgroundImage,
                    inside: cr.left >= fr.left && cr.right <= fr.right + 0.5
                            && cr.top >= fr.top && cr.bottom <= fr.bottom + 0.5,
                    atRight: fr.right - cr.right < 3, w: cr.width, h: cr.height};
        }""", key)
        assert look['list'] is False, look
        assert 'svg' in look['img'], look
        assert look['inside'] and look['atRight'] and look['w'] >= 12 and look['h'] >= 10, look
    key = f'fiber-ext-box-{b}-p1'
    pg.locator(f'[data-lrd-combo-caret="{key}"]').click()
    _menu(pg, key).wait_for(state='visible')
    assert _menu_items(pg, key) == CONNECTORS
    cur = pg.evaluate("""(key) => [...document.querySelector(`[data-lrd-combo-menu="${key}"]`)
        .querySelectorAll('.current')].map(o => o.textContent)""", key)
    assert cur == ['LC duplex']
    under = pg.evaluate("""(key) => {
        const f = document.querySelector(`[data-lrd-field="${key}"]`).getBoundingClientRect();
        const m = document.querySelector(`[data-lrd-combo-menu="${key}"]`).getBoundingClientRect();
        // under the field, or over it when the tray sits low on the window
        return [(m.top >= f.bottom - 1 && m.top - f.bottom < 6)
                    || (m.bottom <= f.top + 1 && f.top - m.bottom < 6),
                Math.abs(m.left - f.left) < 2];
    }""", key)
    assert under == [True, True]
    assert _focused(pg) == key
    pg.locator(f'[data-lrd-combo-caret="{key}"]').click()
    _menu(pg, key).wait_for(state='detached')
    pg.evaluate('() => document.activeElement && document.activeElement.blur()')
    assert ids['errors'] == []


def test_a_pick_from_the_list_is_one_request_and_one_step(page):
    """Caret, then ST: the box end reads ST, ONE write, ONE history entry,
    the list gone and the field let go. Typing narrows the list to what
    matches, and Down then Enter picks from the keys the same way."""
    pg, ids = page
    b = ids['xds'][0]
    key = f'fiber-ext-box-{b}-p1'
    _section(pg, b)
    pg.evaluate(COUNT_PUTS_JS)
    index, _ = _history(pg)
    pg.locator(f'[data-lrd-combo-caret="{key}"]').click()
    _menu(pg, key).get_by_role('option', name='ST', exact=True).click()
    assert settled(pg, lambda: _box_end(pg, b), lambda v: v == 'ST') == 'ST'
    assert settled(pg, lambda: _history(pg), lambda h: h[0] == index + 1) == [index + 1, 'Set Fiber Extension']
    pg.wait_for_timeout(400)
    assert len(_puts(pg)) == 1, _puts(pg)
    assert _history(pg)[0] == index + 1
    assert _menu(pg, key).count() == 0
    assert _focused(pg) != key
    assert pg.locator(f'[data-lrd-field="{key}"]').input_value() == 'ST'
    # the keys: typing narrows, Down lights the match, Enter picks it
    pg.evaluate(COUNT_PUTS_JS)
    field = pg.locator(f'[data-lrd-field="{key}"]')
    field.click()
    field.press('Control+a')
    field.press_sequentially('quad')
    _menu(pg, key).wait_for(state='visible')
    assert _menu_items(pg, key) == ['opticalCON QUAD']
    field.press('ArrowDown')
    field.press('Enter')
    assert settled(pg, lambda: _box_end(pg, b), lambda v: v == 'opticalCON QUAD') == 'opticalCON QUAD'
    assert settled(pg, lambda: _history(pg), lambda h: h[0] == index + 2) == [index + 2, 'Set Fiber Extension']
    pg.wait_for_timeout(400)
    assert len(_puts(pg)) == 1, _puts(pg)
    assert _menu(pg, key).count() == 0
    assert _focused(pg) != key
    assert ids['errors'] == []


def test_a_typed_connector_of_ones_own_still_commits(page):
    """A connector not on the list is typed and kept: Enter writes it once,
    in one entry, and lets go of the field. The trunk end picks the same
    way, and the trunk's own connector picked back is stored as blank."""
    pg, ids = page
    b = ids['xds'][0]
    key = f'fiber-ext-box-{b}-p1'
    _section(pg, b)
    pg.evaluate(COUNT_PUTS_JS)
    index, _ = _history(pg)
    field = pg.locator(f'[data-lrd-field="{key}"]')
    field.click()
    field.press('Control+a')
    field.press_sequentially('SC duplex')
    assert _menu(pg, key).count() == 0     # nothing on the list matches
    field.press('Enter')
    assert settled(pg, lambda: _box_end(pg, b), lambda v: v == 'SC duplex') == 'SC duplex'
    assert settled(pg, lambda: _history(pg), lambda h: h[0] == index + 1) == [index + 1, 'Set Fiber Extension']
    pg.wait_for_timeout(400)
    assert len(_puts(pg)) == 1, _puts(pg)
    assert _focused(pg) != key
    # the trunk end: pick LC duplex, then the MTP's own back (stored blank)
    trunk = f'fiber-ext-trunk-{b}-p1'
    for pick, stored in (('LC duplex', 'LC duplex'), ('MTP / MPO', None)):
        pg.locator(f'[data-lrd-combo-caret="{trunk}"]').click()
        _menu(pg, trunk).get_by_role('option', name=pick, exact=True).click()
        links = _wait_links(pg, b, lambda v, s=stored: v and v['p1']['extension'].get('trunkEnd') == s)
        assert links['p1']['extension'].get('trunkEnd') == stored, links
    assert ids['errors'] == []


def test_esc_closes_the_list_and_nothing_else(page):
    """A click in the EMPTY field opens the list. Esc closes it and stops
    there: the field keeps its focus and what it holds, nothing is written,
    and nothing behind the list hears the key. A click outside closes it
    too. The next Esc, with no list up, goes on as before."""
    pg, ids = page
    b = ids['xds'][0]
    key = f'fiber-ext-box-{b}-p1'
    _section(pg, b)
    pg.evaluate(COUNT_PUTS_JS)
    index, _ = _history(pg)
    pg.evaluate("""() => {
        window.__escHeard = 0;
        if (!window.__escProbe) {
            window.__escProbe = true;
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') window.__escHeard += 1;
            }, true);
        }
    }""")
    # empty the field on the page only, then click into it
    pg.evaluate("(key) => { document.querySelector(`[data-lrd-field=\"${key}\"]`).value = ''; }", key)
    field = pg.locator(f'[data-lrd-field="{key}"]')
    field.click()
    _menu(pg, key).wait_for(state='visible')
    assert _menu_items(pg, key) == CONNECTORS
    field.press('Escape')
    _menu(pg, key).wait_for(state='detached')
    assert pg.evaluate('() => window.__escHeard') == 0
    assert _focused(pg) == key
    assert field.input_value() == ''
    assert pg.locator(f'[data-lrd-cable-sheet="cvt:{b}"]').count() == 1
    # a click outside closes it too
    pg.locator(f'[data-lrd-combo-caret="{key}"]').click()
    _menu(pg, key).wait_for(state='visible')
    pg.locator(f'[data-lrd-fiber-ext="{b}:p1"] .hw-dock-fiber-ext-cap').click()
    _menu(pg, key).wait_for(state='detached')
    # the next Esc, no list up, reaches the page as before
    field.click()
    _menu(pg, key).wait_for(state='visible')
    field.press('Escape')
    assert pg.evaluate('() => window.__escHeard') == 0
    field.press('Escape')
    assert pg.evaluate('() => window.__escHeard') == 1
    pg.wait_for_timeout(300)
    assert _puts(pg) == []
    assert _history(pg)[0] == index
    assert _box_end(pg, b) == 'SC duplex'
    pg.evaluate('() => { document.activeElement && document.activeElement.blur(); '
                'window.app.renderHardwareDock(); }')
    assert ids['errors'] == []


def test_the_unit_stays_beside_the_length_box_at_any_width(page):
    """The line folds as the tray narrows, but the length box and its unit
    are one item: at every width from well under the tray's narrowest cell
    to a wide one, "ft" sits on the length box's line, right after it, and
    "to" on the box end's line, right before it."""
    pg, ids = page
    b = ids['xds'][0]
    _section(pg, b)
    out = pg.evaluate("""(boxId) => {
        const line = document.querySelector(`[data-lrd-fiber-ext="${boxId}:p1"]`);
        const was = line.style.width;
        const bad = [];
        let wrapped = 0;
        for (let w = 200; w <= 640; w += 6) {
            line.style.width = w + 'px';
            const ft = line.querySelector('.hw-dock-cable-ft').getBoundingClientRect();
            const unit = line.querySelector('.hw-dock-fiber-ext-unit');
            const u = unit.getBoundingClientRect();
            const mid = (r) => (r.top + r.bottom) / 2;
            if (line.getBoundingClientRect().height > ft.height * 2) wrapped += 1;
            if (Math.abs(mid(u) - mid(ft)) > 2 || u.left < ft.right || u.left - ft.right > 8
                    || unit.textContent !== 'ft') bad.push([w, ft.top, u.top, ft.right, u.left]);
            // "to" rides on the box end's line, right before it
            const to = line.querySelector('.hw-dock-fiber-ext-to');
            const box = to.querySelector('.hw-dock-fiber-ext-end').getBoundingClientRect();
            const t = to.getBoundingClientRect();
            if (t.height > box.height * 1.5 || box.left - t.left > 40)
                bad.push(['to', w, t.height, box.height, t.left, box.left]);
        }
        line.style.width = was;
        return {bad, wrapped};
    }""", b)
    assert out['bad'] == [], out
    assert out['wrapped'] > 0, out      # the narrow widths did fold the line
    assert ids['errors'] == []
