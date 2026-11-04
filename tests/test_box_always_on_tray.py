"""Every breakout box is on the tray.

Beta.4 QA: an enhanced H_4xfiber in Backup with boxes on OPT 1, 2 and 3-4
took "+ Box → CVT4K-S". With every primary OPT taken the new box resolved
onto OPT 5-6 as a backup (it backs up the CVT10s port by port), and the add
still gave it NovaStar's default backup pair - a box on OPT 7-8 bound
`backupOf` a box that is itself a backup. No strip of the tray drew it:
the binder named it, the user could neither see nor remove it.

* A box that lands on a backup trunk gets no default pair
  (routes_processors.add_cvt).
* A box none of the tray's strips draw - such a box in a file saved before
  the fix, a box delivering no socket - draws on its own, with its ⚙, so
  it can be seen and removed (app-dock.js _dockBuildCard).

Run locally:
    python -m pytest tests/test_box_always_on_tray.py -q
"""

import pytest

H9E = 'novastar-h9-enhanced'
ENHANCED = 'novastar-card-h-4xfiber-enhanced'
CVT10 = 'novastar-cvt10'
CVT4KS = 'novastar-cvt4k-s'


def _ok(resp):
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()


def _enhanced_in_backup(client):
    state = _ok(client.post('/api/processors', json={'deviceId': H9E}))
    pid = state['resolved'][-1]['id']
    state = _ok(client.put(f'/api/processors/{pid}/slots/0',
                           json={'deviceId': ENHANCED}))
    cid = state['resolved'][-1]['slots'][0]['card']['id']
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': 'backup'}))
    for device_id in (CVT10, CVT10, CVT4KS):
        _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                        json={'deviceId': device_id, 'pair': False}))
    return pid, cid


def _boxes(state, cid):
    for proc in state['resolved']:
        for slot in proc['slots']:
            if slot['card'] and slot['card']['id'] == cid:
                return slot['card']['cvts']
    raise AssertionError(cid)


def test_a_box_landing_on_a_backup_trunk_gets_no_pair(client):
    pid, cid = _enhanced_in_backup(client)
    state = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                            json={'deviceId': CVT4KS}))
    boxes = _boxes(state, cid)
    assert [b['displayTitle'] for b in boxes] == [
        'CVT10-S A', 'CVT10-S B', 'CVT4K-S C-D', 'CVT4K-S E-F'], boxes
    # the new box is a backup by where it landed, and nothing backs it up
    assert boxes[-1]['copyRole'] == 'backup'
    assert not any(b.get('backupOf') == boxes[-1]['id'] for b in boxes)


def test_a_primary_box_still_gets_its_default_pair(client):
    state = _ok(client.post('/api/processors', json={'deviceId': H9E}))
    pid = state['resolved'][-1]['id']
    state = _ok(client.put(f'/api/processors/{pid}/slots/0',
                           json={'deviceId': ENHANCED}))
    cid = state['resolved'][-1]['slots'][0]['card']['id']
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': 'backup'}))
    state = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                            json={'deviceId': CVT10}))
    boxes = _boxes(state, cid)
    assert len(boxes) == 2 and boxes[1]['backupOf'] == boxes[0]['id'], boxes


# ── the tray ──────────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# The old file's shape: the backup box on OPT 5-6 with a "pair" of its own
# on OPT 7-8, stored the way the add used to store it.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.distros = [];
    delete proj.port_assignments; delete proj.snakes; delete proj.fiberCables;
    proj.processors = [{id: 'proc1', deviceId: 'novastar-h9-enhanced', name: '',
        mode: null, redundancy: false, slots: [
            {index: 0, card: {id: 'card2', deviceId: 'novastar-card-h-4xfiber-enhanced',
                name: '', mode: 'backup', cvts: [
                {id: 'cvt3', deviceId: 'novastar-cvt10', name: '', mode: 'default', trunk: 0},
                {id: 'cvt4', deviceId: 'novastar-cvt10', name: '', mode: 'default', trunk: 1},
                {id: 'cvt5', deviceId: 'novastar-cvt4k-s', name: '', mode: 'default', trunk: 2},
                {id: 'cvt6', deviceId: 'novastar-cvt4k-s', name: '', mode: 'default'},
                {id: 'cvt7', deviceId: 'novastar-cvt4k-s', name: '', mode: 'default',
                 backupOf: 'cvt6'}]}}]}];
    proj.next_processor_seq = 8;
    await j('PUT', '/api/project', proj);
    const app = window.app;
    app.project = await j('GET', '/api/project');
    await app.refreshProcessors();
    app.renderHardwareDock();
    return (app._processorsResolved[0].slots[0].card.cvts || []).map(b => b.id);
}"""


@pytest.fixture()
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete === true")
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    yield pg
    context.close()


def test_a_backup_of_a_backup_from_an_old_file_is_on_the_tray(page):
    ids = page.evaluate(SEED_JS)
    page.wait_for_timeout(500)
    assert ids == ['cvt3', 'cvt4', 'cvt5', 'cvt6', 'cvt7']
    missing = page.evaluate("""(ids) => ids.filter(id =>
        !document.querySelector(`[data-hwpop="box-${id}"]`))""", ids)
    assert missing == [], f'boxes with no place on the tray: {missing}'
    # ...and its gear removes it
    page.locator('[data-hwpop="box-cvt7"]').first.click()
    page.wait_for_timeout(300)
    page.locator('#hw-gear-popover .hw-pop-remove').click()
    page.wait_for_function("() => !window.app._processorsResolved[0].slots[0].card.cvts"
                           ".some(b => b.id === 'cvt7')")
