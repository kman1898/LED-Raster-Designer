"""A full fiber cable is said plainly and never sent for.

Beta.4 QA: picking TAC A for a box's link once its strands were all taken
was refused with "TAC A has no 2 free strands left." and a 400 in the
console. Refusals are expected, so the pick no longer goes out: the link's
cable select lists a TAC or MTP without the strands this link needs as
"TAC A · 4 · full", disabled (app-dock-cable-sheets.js
_dockBuildFiberSelect). A client that still asks is refused in plain words
(routes_processors._fiber_link_strands): "TAC A is full: every strand is
in use.", or "TAC A has 1 free strand and this link needs 2."

Run locally:
    python -m pytest tests/test_fiber_full_cable.py -q
"""

import pytest


def _ok(resp):
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()


def _three_boxes(client, strands):
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}))
    pid = st['resolved'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0',
                        json={'deviceId': 'novastar-card-h-4xfiber'}))
    cid = st['resolved'][-1]['slots'][0]['card']['id']
    for _ in range(3):
        st = _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                             json={'deviceId': 'novastar-cvt10', 'pair': False}))
    boxes = [b['id'] for b in st['resolved'][-1]['slots'][0]['card']['cvts']]
    tac = _ok(client.post('/api/fiber-cables',
                          json={'kind': 'tac', 'strands': strands}))['fiberCables'][-1]
    return pid, boxes, tac['id']


def _link(client, pid, box, cable):
    return client.put(f'/api/processors/{pid}/cvts/{box}/fiber-links/p1',
                      json={'cable': cable})


def test_a_full_tac_is_said_to_be_full(client):
    pid, boxes, tac = _three_boxes(client, 4)
    _ok(_link(client, pid, boxes[0], tac))
    _ok(_link(client, pid, boxes[1], tac))
    resp = _link(client, pid, boxes[2], tac)
    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'TAC A is full: every strand is in use.'


def test_a_tac_short_of_strands_says_what_it_has_and_what_is_needed(client):
    pid, boxes, tac = _three_boxes(client, 3)
    _ok(_link(client, pid, boxes[0], tac))
    resp = _link(client, pid, boxes[1], tac)
    assert resp.status_code == 400
    assert resp.get_json()['error'] == \
        'TAC A has 1 free strand and this link needs 2.'


# ── the sheet ─────────────────────────────────────────────────────────────

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
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`, {deviceId: 'novastar-card-h-4xfiber'});
    const cid = st.processors[0].slots[0].card.id;
    for (let i = 0; i < 3; i++) {
        st = await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`,
                     {deviceId: 'novastar-cvt10', pair: false});
    }
    const boxes = st.processors[0].slots[0].card.cvts.map(b => b.id);
    st = await j('POST', '/api/fiber-cables', {kind: 'tac', strands: 4});
    const tac = st.fiberCables[st.fiberCables.length - 1].id;
    for (const b of boxes.slice(0, 2)) {
        await j('PUT', `/api/processors/${pid}/cvts/${b}/fiber-links/p1`, {cable: tac});
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    await app.refreshProcessors();
    app.renderHardwareDock();
    return {boxes, tac};
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


def test_the_sheet_lists_a_full_tac_as_full_and_cannot_pick_it(page):
    ids = page.evaluate(SEED_JS)
    page.wait_for_timeout(500)
    third = ids['boxes'][2]
    page.locator(f'[data-lrd-field="data-cable-sheet-{third}"]').first.click()
    page.wait_for_timeout(400)
    opts = page.locator(f'[data-lrd-field="fiber-link-cable-{third}-p1"]').evaluate(
        "s => [...s.options].filter(o => o.value === '%s')"
        ".map(o => [o.textContent, o.disabled])" % ids['tac'])
    assert opts == [['TAC A · 4 · full', True]], opts
    # a box that already holds strands on it still picks it freely
    first = ids['boxes'][0]
    page.locator(f'[data-lrd-field="data-cable-sheet-{first}"]').first.click()
    page.wait_for_timeout(400)
    opts = page.locator(f'[data-lrd-field="fiber-link-cable-{first}-p1"]').evaluate(
        "s => [...s.options].filter(o => o.value === '%s')"
        ".map(o => [o.textContent, o.disabled])" % ids['tac'])
    assert opts == [['TAC A · 4', False]], opts
