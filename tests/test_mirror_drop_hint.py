"""A full card whose copy output backs up says how to make a mirror.

Beta.4 QA: a card already full with one screen, dropped on a second screen
with no ports, could only be making a copy - and where the card's copy
output was set to back up (a VX600 Pro in Backup, an MCTRL R5 with its OPT
2 box on Backup) the drop said only "VX600 Pro has no free ports". It now
says the way to do it, like the other mirror refusals
(app-mirror-screens.js _copyDropHint): "switch VX600 Pro to Copy mode",
"set the box on OPT 2 to Mirror", "put a box on OPT 2 and set it to
Mirror". A unit with no copy setting (an MCTRL660 Pro: its OPT 2 only
backs up) keeps the plain refusal.

Run locally:
    python -m pytest tests/test_mirror_drop_hint.py -q
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# SL big enough to fill any of these units, SR a second screen with none.
SEED_JS = """async ([device, box]) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.fiberCables; delete proj.snakes;
    await j('PUT', '/api/project', proj);
    const sl = await j('POST', '/api/layer/add', {name: 'SL', columns: 20, rows: 8,
        cabinet_width: 256, cabinet_height: 256, processorType: 'novastar-armor'});
    const sr = await j('POST', '/api/layer/add', {name: 'SR', columns: 4, rows: 3,
        cabinet_width: 256, cabinet_height: 256, processorType: 'novastar-armor',
        offset_x: 6000});
    let st = await j('POST', '/api/processors', {deviceId: device});
    const pid = st.processors[0].id;
    const cid = st.processors[0].slots[0].card.id;
    if (box) await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`, box);
    const app = window.app;
    app.project = await j('GET', '/api/project');
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(sl.id), cardId: cid});
    await app.refreshPortAssignment();
    const found = app._dockFindCard(cid);
    const target = app._dockDataScreenTarget(
        {payload: {type: 'card', cardId: cid, title: found.card.deviceName}},
        String(sr.id), null);
    return {free: app._assignment.cards.find(c => c.cardId === cid).free,
            pill: target.pill};
}"""


@pytest.fixture(scope="module")
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


@pytest.mark.parametrize('device,box,said', [
    ('novastar-vx600-pro', {'deviceId': 'novastar-cvt10'},
     'VX600 Pro has no free ports. To make SR a copy of SL, switch VX600 '
     'Pro to Copy mode.'),
    ('novastar-mctrl-r5', None,
     'MCTRL R5 has no free ports. To make SR a copy of SL, put a box on '
     'OPT 2 and set it to Mirror.'),
    ('novastar-mctrl-r5', {'deviceId': 'novastar-cvt10', 'trunk': 1},
     'MCTRL R5 has no free ports. To make SR a copy of SL, set the box on '
     'OPT 2 to Mirror.'),
    ('novastar-mctrl660-pro', None, 'MCTRL660 Pro has no free ports'),
])
def test_the_refusal_says_how_to_make_the_copy(page, device, box, said):
    out = page.evaluate(SEED_JS, [device, box])
    assert out['free'] == 0, out
    assert out['pill'] == {'ok': False, 'message': said}, out
