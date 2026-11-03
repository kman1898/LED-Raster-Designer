"""Ports no backup covers are said, on the box and in the processor gear.

Owner, 2026-11-03: a CVT4K-S backing up two CVT10s carries 8 ports per
input, so ports 9-10 of each CVT10 have no backup, and nothing said so.
The uncovered ports are read off the actual coverage, never hard-coded
(processor_catalog._note_unbacked_ports: a backed-up box's own ports with
no `backedBy`), so any box with more ports than its backup carries reads
right. The tray's box header says "ports 9-10 have no backup"; the
processor's gear says it per box beside its capacity line.

Run locally:
    python -m pytest tests/test_unbacked_box_ports.py -q
"""

import pytest

H9E = 'novastar-h9-enhanced'
ENHANCED = 'novastar-card-h-4xfiber-enhanced'
CVT10 = 'novastar-cvt10'
CVT4KS = 'novastar-cvt4k-s'


def _ok(resp):
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()


def _enhanced(client):
    st = _ok(client.post('/api/processors', json={'deviceId': H9E}))
    pid = st['resolved'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0', json={'deviceId': ENHANCED}))
    cid = st['resolved'][-1]['slots'][0]['card']['id']
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': 'backup'}))
    return pid, cid


def _boxes(state):
    return {b['displayTitle']: b['unbackedPorts']
            for b in state['resolved'][-1]['slots'][0]['card']['cvts']}


def test_two_cvt10s_behind_one_cvt4k_s_leave_9_and_10_unbacked(client):
    pid, cid = _enhanced(client)
    for device_id in (CVT10, CVT10, CVT4KS):
        _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                        json={'deviceId': device_id, 'pair': False}))
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': CVT4KS}))
    assert _boxes(st) == {'CVT10 A': [9, 10], 'CVT10 B': [9, 10],
                          'CVT4K-S C-D': [], 'CVT4K-S E-F': []}


def test_a_full_pair_and_an_unbacked_box_say_nothing(client):
    pid, cid = _enhanced(client)
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': CVT10}))
    st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                         json={'deviceId': CVT10, 'pair': False}))
    # A backed by its pair in full; B backed by nothing at all (not "no
    # backup on 1-10": a box nobody backs up is not a shortfall)
    assert _boxes(st) == {'CVT10 A': [], 'CVT10 E': [], 'CVT10 B': []}


# ── the tray and the gear ─────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.fiberCables; delete proj.snakes;
    await j('PUT', '/api/project', proj);
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9-enhanced'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-4xfiber-enhanced'});
    const cid = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cid}`, {mode: 'backup'});
    for (const d of ['novastar-cvt10', 'novastar-cvt10', 'novastar-cvt4k-s', 'novastar-cvt4k-s']) {
        st = await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`, {deviceId: d, pair: false});
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    await app.refreshProcessors();
    app.renderHardwareDock();
    return {pid, boxes: st.processors[0].slots[0].card.cvts.map(b => b.id)};
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


def test_the_box_header_and_the_processor_gear_say_it(page):
    ids = page.evaluate(SEED_JS)
    page.wait_for_timeout(500)
    a, b, cd, ef = ids['boxes']
    notes = page.evaluate("""(ids) => ids.map(id => {
        const el = document.querySelector(`[data-lrd-field="box-unbacked-${id}"]`);
        return el ? el.textContent : null;
    })""", ids['boxes'])
    assert notes == ['ports 9-10 have no backup', 'ports 9-10 have no backup',
                     None, None], notes
    page.locator(f'[data-hwpop="proc-{ids["pid"]}"]').first.click()
    page.wait_for_timeout(300)
    line = page.evaluate("""(pid) => {
        const el = document.querySelector(`[data-lrd-field="processor-unbacked-${pid}"]`);
        return el ? el.textContent : null;
    }""", ids['pid'])
    assert line == ('CVT10 A ports 9-10 have no backup. '
                    'CVT10 B ports 9-10 have no backup.'), line
