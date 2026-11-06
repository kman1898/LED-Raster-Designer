"""What a DATA WIRING sheet's breakout box names between the box and its
trunk (owner, 2026-10-29).

A friend's 1.5.3 binder read "XD B · slot 1 · trunk B" on an SX40 nobody
had named - the slot a one-box unit sits in internally, which no SX40 has.
The part between the box and its trunk is now:

  - on a one-box unit (an SX40): the model and the name typed on it,
    "XD B · SX40 S3 · trunk B" - and nothing where nobody named it,
    "XD B · trunk B", never "slot 1" or the bare model;
  - a name that already starts with the model is not doubled;
  - on a card-based processor (an H9): the card by name, else "Card N" by
    its slot (owner, 2026-10-29: "Card 1, 2, 3 etc instead of H_16").

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_wiring_box_unit_name.py -v --browser chromium
"""

import re

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# WALL on one SX40, its ports placed on its XDs; an H9 with one
# 16-port card beside it, nothing on it.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits; delete proj.binder;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 12, rows: 4,
                                                     cabinet_width: 200, cabinet_height: 200});
    await j('PUT', `/api/layer/${wall.id}`, {processorType: 'brompton'});
    let st = await j('POST', '/api/processors', {deviceId: 'brompton-sx40'});
    const sx = st.processors[0];
    st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const h9 = st.processors.find(p => p.id !== sx.id);
    st = await j('PUT', `/api/processors/${h9.id}/slots/0`,
                 {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const h9card = st.processors.find(p => p.id === h9.id).slots[0].card.id;
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('wiring_unit_name_setup');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(wall.id), cardId: sx.slots[0].card.id, lastIndex: 19});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.resetHistory('Wiring Unit Name Seed');
    return {sx: sx.id, h9: h9.id, h9card};
}"""

# Every box title on the screen's DATA WIRING sheets.
TITLES_JS = """() => {
    const app = window.app;
    const opts = { sheet: 'tabloid', palette: 'colour', sides: {power: true, data: true},
                   scope: {kind: 'show'}, cover: false, pull: false, hardware: false };
    const plan = app.planBinder(opts);
    const titles = [];
    plan.forEach((p, i) => {
        if (!/data wiring/i.test(p.title || '')) return;
        const r = app.renderBinderPage(opts, i);
        for (const h of ((r.wiring || {}).halves || [])) {
            for (const b of (h.blocks || [])) titles.push(b.title);
        }
    });
    return { titles: [...new Set(titles)].sort(), plan: plan.map(p => p.title) };
}"""

RENAME_JS = """async ([id, name]) => {
    await fetch(`/api/processors/${id}`, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name})});
    await window.app.refreshProcessors();
    await window.app.refreshPortAssignment();
}"""

RENAME_CARD_JS = """async ([pid, cid, name]) => {
    await fetch(`/api/processors/${pid}/cards/${cid}`, {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name})});
    await window.app.refreshProcessors();
}"""

HOME_JS = """(cardId) => window.app._bPortHome(cardId, 1).cardTitle"""


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
    pg.wait_for_timeout(800)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _titles(pg):
    out = pg.evaluate(TITLES_JS)
    assert out['titles'], ('no DATA WIRING sheet drew a box', out['plan'])
    return out['titles']


def test_an_unnamed_sx40_names_no_unit_between_box_and_trunk(page):
    pg, ids = page
    pg.evaluate(RENAME_JS, [ids['sx'], ''])
    titles = _titles(pg)
    assert titles and all(re.fullmatch(r'XD [A-D] · trunk [A-D]', t) for t in titles), titles
    assert ids['errors'] == []


def test_a_named_sx40_reads_model_then_name(page):
    pg, ids = page
    pg.evaluate(RENAME_JS, [ids['sx'], 'S3'])
    titles = _titles(pg)
    assert all(' · SX40 S3 · trunk ' in t for t in titles), titles
    assert not any('slot' in t.lower() for t in titles), titles


def test_a_name_already_starting_with_the_model_is_not_doubled(page):
    pg, ids = page
    pg.evaluate(RENAME_JS, [ids['sx'], 'SX40 MAIN'])
    titles = _titles(pg)
    assert all(' · SX40 MAIN · trunk ' in t for t in titles), titles
    pg.evaluate(RENAME_JS, [ids['sx'], ''])


def test_a_card_based_processor_names_its_card_or_its_slot(page):
    pg, ids = page
    assert pg.evaluate(HOME_JS, ids['h9card']) == 'Card 1'
    pg.evaluate(RENAME_CARD_JS, [ids['h9'], ids['h9card'], 'SR'])
    assert pg.evaluate(HOME_JS, ids['h9card']) == 'SR'
    pg.evaluate(RENAME_CARD_JS, [ids['h9'], ids['h9card'], ''])
