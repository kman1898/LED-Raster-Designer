"""An unnamed card on a card-based processor reads "Card N" (owner,
2026-10-29: "we should show it as Card 1, 2, 3 etc instead of H_16 which
gets confusing" - option A: "Card 1, Card 2, Card 3 everywhere. The model
stays where you pull gear: the binder's CARDS table and pull page
hardware").

  - Only the H series, the MX2000 and the MX6000 hold cards
    (procIsCardBased / is_card_based); every other processor never says
    card or slot, and its naming is untouched.
  - N is the slot the card sits in, counted from one: a card in slot 4
    with slot 3 empty is Card 4.
  - A name typed on the card always wins.
  - The model (H_16xRJ45+2xfiber) is printed only on the binder's Cards
    table and its pull page's Hardware (and stands under the card's name
    in its own ⚙); the tray, the processor's ⚙, the data sheets and the
    data wiring sheets say Card N.

Also pinned here, from the same pass: the Cards table's BACKUP column says
each card's redundancy in the app's words ("1:1, backed up by Card 2",
"backs up Card 1", "1:1, no partner", "Sequential", "OPT Split"), never the
stored id ("1to1", "halves"); and the pull page's Hardware lists the 1:1
backup card a screen's returns land on - it is a card in the rack to pull.

Run locally (each session takes its own free port):
    python3 -m pytest tests/test_card_names.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import port_assignment as pa  # noqa: E402
import processor_catalog as catalog  # noqa: E402

MODEL = 'H_16xRJ45+2xfiber'
CARD = 'novastar-card-h-16xrj45-2xfiber'


# ── the server's reading ──────────────────────────────────────────────────

def _h9(slots):
    """A raw H9 with the given slot indexes filled, unnamed."""
    proc = {'id': 'p1', 'deviceId': 'novastar-h9', 'name': '',
            'slots': [{'index': i, 'card': None} for i in range(4)]}
    for i in slots:
        proc['slots'][i]['card'] = {'id': f'c{i}', 'deviceId': CARD, 'name': ''}
    return proc


def test_an_unnamed_card_is_card_n_by_its_slot():
    proc = _h9([0, 1, 3])
    cards = [s['card'] for s in proc['slots'] if s['card']]
    assert [catalog.card_slot_title(c, proc) for c in cards] == ['Card 1', 'Card 2', 'Card 4']
    assert [catalog.card_display_name(c, proc) for c in cards] == ['Card 1', 'Card 2', 'Card 4']
    # the resolved tree reads the same
    res = catalog.resolve_all([proc])[0]
    rcards = [s['card'] for s in res['slots'] if s.get('card')]
    assert [catalog.card_display_name(c, res) for c in rcards] == ['Card 1', 'Card 2', 'Card 4']


def test_a_typed_card_name_wins():
    proc = _h9([0])
    proc['slots'][0]['card']['name'] = 'SR'
    assert catalog.card_display_name(proc['slots'][0]['card'], proc) == 'SR'


def test_a_processor_without_cards_never_says_card():
    proc = {'id': 'p2', 'deviceId': 'brompton-sx40', 'name': '',
            'slots': [{'index': 0, 'card': {'id': 'x', 'deviceId': None, 'name': '', 'fixed': True}}]}
    assert catalog.card_slot_title(proc['slots'][0]['card'], proc) == ''


def test_the_backup_card_says_whose_by_card_n():
    proc = _h9([0, 1, 3])
    proc['redundancy'] = True
    proc['slots'][0]['card']['backupCardId'] = 'c1'
    res = catalog.resolve_all([proc])[0]
    back = res['slots'][1]['card']
    assert back['backupFor']['title'] == 'Card 1', back['backupFor']
    main_port = res['slots'][0]['card']['ports'][0]
    assert main_port['backedBy']['cardTitle'] == 'Card 2', main_port['backedBy']
    assert back['ports'][0]['backsUp']['cardTitle'] == 'Card 1', back['ports'][0]['backsUp']


def test_a_message_names_the_processor_and_card_n():
    proc = _h9([0, 3])
    by_id = {c['cardId']: c for c in pa.cards_in([proc])}
    assert pa._card_title(by_id['c0']) == 'H9 Card 1'
    assert pa._card_title(by_id['c3']) == 'H9 Card 4'


# ── the app ───────────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_processor_panel import (  # noqa: E402
    BAR_JS, FETCH_COUNT_JS, OPEN_GEAR_JS, app_ready, dock_still, quiet,
)
from test_binder_tables import OPTS, SHEETS_JS  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# One wall on an H9 holding three unnamed H_16xRJ45+2xfiber cards in slots
# 1, 2 and 4 (slot 3 empty): card 1 backed up 1:1 by card 2, the wall's
# other ports on the slot-4 card at 1:1 with no partner.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder; delete proj.snakes;
    delete proj.fiberCables;
    await j('PUT', '/api/project', proj);
    const wall = await j('POST', '/api/layer/add', {name: 'WALL', columns: 64, rows: 28,
        cabinet_width: 60, cabinet_height: 120, flowPattern: 'tl-h',
        processorType: 'novastar-armor'});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    for (const i of [0, 1, 3]) {
        st = await j('PUT', `/api/processors/${pid}/slots/${i}`, {deviceId: '%(card)s'});
    }
    const slots = st.processors[0].slots;
    const [c1, c2, c4] = [0, 1, 3].map(i => slots[i].card.id);
    await j('PUT', `/api/processors/${pid}`, {redundancy: true});
    await j('PUT', `/api/processors/${pid}/cards/${c1}`, {backupCardId: c2});
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('card_names_seed');
    const layer = app.project.layers.find(l => l.name === 'WALL');
    app.selectLayer(layer);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(layer.id), cardId: c1, lastIndex: 15});
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
        {layerId: String(layer.id), cardId: c4, lastIndex: 27});
    for (const id of [c1, c2, c4]) {
        try {
            localStorage.removeItem('ledRasterPanelCollapsed_hwdock-card-' + id);
        } catch (e) { /* blocked storage never held the key */ }
    }
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Card Names Seed');
    return {pid, c1, c2, c4, layerId: String(layer.id)};
}""" % {'card': CARD}

TRAY_JS = """(ids) => {
    const head = (cid) => document.querySelector(`[data-hwdock="card-${cid}"]`);
    const label = (cid) => {
        const h = head(cid);
        const el = h && h.querySelector('.hw-dock-unit-name');
        return el ? el.textContent : null;
    };
    const pill = (cid) => {
        const h = head(cid);
        const el = h && h.querySelector('.hw-dock-redpill');
        return el ? el.textContent : null;
    };
    return {labels: [ids.c1, ids.c2, ids.c4].map(label),
            pills: [ids.c1, ids.c2, ids.c4].map(pill),
            drop: window.app._dockDropUnit({type: 'processor', processorId: ids.pid}).title};
}"""

PICKER_JS = """(cid) => {
    const pop = document.getElementById('hw-gear-popover');
    const sel = pop && pop.querySelector(`[data-lrd-field="processor-card-backup-${cid}"]`);
    return sel ? Array.from(sel.options).map(o => o.textContent) : null;
}"""

CARD_GEAR_JS = """() => {
    const pop = document.getElementById('hw-gear-popover');
    if (!pop) return null;
    const head = pop.querySelector('.hw-pop-heading');
    const model = pop.querySelector('.hw-pop-model');
    const red = Array.from(pop.querySelectorAll('div'))
        .map(d => d.textContent).find(t => /^Redundancy: /.test(t));
    // the title bar carries the close ×
    return {heading: head ? head.textContent.replace(/×$/, '').trim() : null,
            model: model ? model.textContent : null, redundancy: red || null};
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    app_ready(pg)
    ids = pg.evaluate(SEED_JS)
    quiet(pg)
    pg.locator('[data-mode="data-flow"]').click()
    dock_still(pg)
    yield pg, ids, errors
    context.close()


def test_the_tray_reads_card_n(page):
    pg, ids, errors = page
    out = pg.evaluate(TRAY_JS, ids)
    assert out['labels'] == ['Card 1', 'Card 2 (backs up Card 1)', 'Card 4'], out
    assert out['pills'] == ['R 1:1 → Card 2 in H9', None, 'R 1:1, no partner'], out
    # a processor's drag goes by its first card
    assert out['drop'] == 'Card 1', out
    assert errors == []


def test_the_processor_gear_rows_and_partner_pick_read_card_n(page):
    pg, ids, _errors = page
    assert pg.evaluate(OPEN_GEAR_JS, f"proc-{ids['pid']}")
    quiet(pg)
    bar = pg.evaluate(BAR_JS, ids['pid'])
    assert bar['rows'] == ['Slot 1 · Card 1', 'Slot 2 · Card 2', 'Slot 4 · Card 4'], bar
    # Card 1's pick reads its partner and the free card by Card N, with
    # the house separator (no spaced hyphen)
    opts = pg.evaluate(PICKER_JS, ids['c1'])
    assert opts == ['backed up by…', 'Card 2 in H9 · 16 ports',
                    'Card 4 in H9 · 16 ports'], opts
    assert not any(MODEL in o for o in opts), opts
    # Card 4 is offered neither Card 2 (it backs up Card 1) nor Card 1 (a
    # main with a backup of its own): the server refuses both, and the
    # pick used to offer them and draw a 400 (beta.4 QA).
    assert pg.evaluate(PICKER_JS, ids['c4']) == ['backed up by…']
    # Card 2 is Card 1's backup: no pick of its own, it says whose
    # (owner, beta.4: no backup of a backup).
    assert pg.evaluate(PICKER_JS, ids['c2']) is None
    fact = pg.evaluate("""(cid) => {
        const pop = document.getElementById('hw-gear-popover');
        const el = pop && pop.querySelector(
            `[data-lrd-field="processor-card-backupfor-${cid}"]`);
        return el ? el.textContent : null;
    }""", ids['c2'])
    assert fact == 'backs up Card 1', fact


def test_the_card_gear_is_headed_card_n_with_its_model_under(page):
    pg, ids, _errors = page
    assert pg.evaluate(OPEN_GEAR_JS, f"card-{ids['c1']}")
    quiet(pg)
    assert pg.evaluate(CARD_GEAR_JS) == {
        'heading': 'Card 1', 'model': MODEL,
        'redundancy': 'Redundancy: 1:1, backed up by Card 2 in H9'}
    assert pg.evaluate(OPEN_GEAR_JS, f"card-{ids['c2']}")
    quiet(pg)
    assert pg.evaluate(CARD_GEAR_JS) == {
        'heading': 'Card 2', 'model': MODEL, 'redundancy': 'Redundancy: backs up Card 1'}


CAPACITY_JS = """() => {
    const pop = document.getElementById('hw-gear-popover');
    return pop ? [...pop.querySelectorAll('div')].map(d => d.textContent)
        .filter(t => /^\\d+ (\\/ \\d+ ports( · \\d+ backup)?|backup ports)$/.test(t))
        : null;
}"""


def test_the_capacity_rows_count_usable_ports_with_the_backups_beside(page):
    """Owner, 2026-11-03: "40 / 40 ports · 40 backup", never "80 / 80
    ports". Three 16-port cards, Card 2 Card 1's 1:1 backup: the
    processor reads 32 usable of 32 with 16 backup; Card 1 reads its own
    16; Card 2 is nothing but returns."""
    pg, ids, _errors = page
    assert pg.evaluate(OPEN_GEAR_JS, f"proc-{ids['pid']}")
    quiet(pg)
    assert pg.evaluate(CAPACITY_JS) == ['32 / 32 ports · 16 backup']
    assert pg.evaluate(OPEN_GEAR_JS, f"card-{ids['c1']}")
    quiet(pg)
    assert pg.evaluate(CAPACITY_JS) == ['16 / 16 ports']
    assert pg.evaluate(OPEN_GEAR_JS, f"card-{ids['c2']}")
    quiet(pg)
    assert pg.evaluate(CAPACITY_JS) == ['16 backup ports']


@pytest.fixture(scope="module")
def sheets(page):
    pg, _ids, errors = page
    project = pg.evaluate("() => fetch('/api/project').then(r => r.json())")
    out = pg.evaluate(SHEETS_JS, [project, OPTS])
    assert not errors, errors[:3]
    return out['pages']


def _texts(page):
    return [o['t'] for o in page['texts']]


def test_no_binder_sheet_says_slot_or_a_stored_id(sheets):
    texts = [t for p in sheets for t in _texts(p)]
    assert not [t for t in texts if 'slot ' in t.lower()], [t for t in texts if 'slot' in t.lower()]
    assert '1to1' not in texts and 'halves' not in texts


def test_the_model_is_printed_only_where_gear_is_pulled(sheets):
    """The Cards table on the processor's page and the pull page's
    Hardware; never a data sheet's band or a wiring sheet's box."""
    with_model = sorted({p['kind'] for p in sheets if any(MODEL in t for t in _texts(p))})
    data = [p for p in sheets if p['kind'] == 'data' or 'wiring' in (p['title'] or '').lower()]
    assert data, [p['title'] for p in sheets]
    for p in data:
        assert not [t for t in _texts(p) if MODEL in t], (p['title'], [t for t in _texts(p) if MODEL in t])
    assert with_model, 'the model is printed nowhere'


def test_the_cards_table_names_each_card_and_its_backup_in_the_apps_words(sheets):
    texts = [t for p in sheets for t in _texts(p)]
    for name in ('Card 1', 'Card 2', 'Card 4'):
        assert name in texts, name
    joined = ' '.join(texts)
    assert 'backed up by Card 2' in joined, 'card 1 does not name its partner'
    assert 'backs up Card 1' in texts, 'card 2 does not say whose backup it is'
    assert any('no partner' in t for t in texts), 'card 4 does not say it has no partner'


def test_the_data_sheet_bands_and_outputs_read_card_n(sheets):
    texts = [t for p in sheets if p['kind'] == 'data' for t in _texts(p)]
    assert 'H9 Card 1 · 16 ports' in texts, texts[:60]
    assert 'H9 Card 2 · 16 ports' in texts, texts[:60]
    assert 'H9 Card 1 · 1' in texts and 'H9 Card 2 · 1' in texts, texts[:80]


def test_the_pull_page_hardware_lists_every_card_with_its_model(sheets):
    """Card 1 and Card 4 carry the wall's ports, Card 2 its returns: all
    three are cards to pull, each with its model."""
    rows = []
    for p in sheets:
        t = _texts(p)
        if 'HARDWARE' not in t:
            continue
        for i, w in enumerate(t):
            if w.startswith('H9 Card '):
                rows.append((w, t[i + 1] if i + 1 < len(t) else None))
    assert rows == [('H9 Card 1', MODEL), ('H9 Card 2', MODEL), ('H9 Card 4', MODEL)], rows
