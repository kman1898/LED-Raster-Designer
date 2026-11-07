"""MIXED redundancy on one processor, in the browser.

The owner (2026-10-29): "sometimes on say H series i have 3 16 port cards.
and i want card 1 and 2 to be primary and backup but then card 3 i want
port level backup" - and, of the three ways offered, "i want to leave the
bar. so i think adding mixed makes the most sense."

So behind a chassis's ⚙ the REDUNDANCY bar is Off · Per card · Per port ·
Mixed (a standalone unit keeps Off · Backed up · Per port). Under Mixed
there is one row per slot: the card picks 1:1 or a port shape on one chip
row (the same chips and tips Per port draws, with 1:1 in front), and at
1:1 the same partner pick Per card draws sits under it. Each gesture
writes only its card, one undo step each, and the bar stays at Mixed. A
card that is another card's 1:1 backup reads "Backup for <card>" and
offers nothing. Per card / Per port from Mixed convert every card as they
always did.

Downstream reads per card, never per processor: the tray's pills, the
binder's PRIMARY / BACKUP ports table, its Cards table and Redundancy
line, the pull sheet's backup runs - checked here on a chassis with cards
1 + 2 paired 1:1 and card 3 at halves, then at sequential.

The server half (the stored pick, undo/redo, the file, the port
assignment) is tests/test_mixed_redundancy.py.

Run locally:
    python -m pytest tests/test_mixed_redundancy_ui.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_processor_panel import (  # noqa: E402
    APP_READY_JS, BAR_JS, CLICK_CHIP_JS, CLICK_SEG_JS, FETCH_COUNT_JS,
    HISTORY_LEN_JS, LAST_ACTION_JS, OPEN_GEAR_JS, RESET_LAYERS_JS,
    app_ready, dock_still, quiet,
)
from test_binder_tables import (  # noqa: E402
    OPTS, SEED_BACKUP_JS, SHEETS_JS, _all_rows, _ports_table,
)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    app_ready(pg)
    assert pg.evaluate(RESET_LAYERS_JS), "test project was not created"
    quiet(pg)
    pg.locator('[data-mode="data-flow"]').click()
    dock_still(pg)
    yield pg
    assert not errors, errors[:3]
    context.close()


# An H9 "SR" with three 16-port cards, redundancy on (every card at 1:1,
# none paired), and a standalone MX20 beside it.
SEED_JS = """
async () => {
    const state = await (await fetch('/api/processors')).json();
    for (const p of state.processors) {
        await fetch(`/api/processors/${p.id}`, { method: 'DELETE' });
    }
    const send = (url, method, body) => fetch(url, {
        method, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    }).then(r => r.json());
    let st = await send('/api/processors', 'POST',
                        { deviceId: 'novastar-h9', name: 'SR' });
    const proc = st.resolved[st.resolved.length - 1];
    for (const i of [0, 1, 2]) {
        st = await send(`/api/processors/${proc.id}/slots/${i}`, 'PUT',
                        { deviceId: 'novastar-card-h-16xrj45-2xfiber' });
    }
    const cards = st.resolved.find(p => p.id === proc.id)
        .slots.filter(s => s.card).map(s => s.card.id);
    await send(`/api/processors/${proc.id}`, 'PUT', { redundancy: true });
    st = await send('/api/processors', 'POST', { deviceId: 'novastar-mx20' });
    const mx = st.resolved[st.resolved.length - 1];
    await send(`/api/processors/${mx.id}`, 'PUT', { name: 'MX', redundancy: true });
    for (const id of cards.concat([mx.slots[0].card.id])) {
        try {
            localStorage.removeItem('ledRasterPanelCollapsed_hwdock-card-' + id);
        } catch (e) { /* blocked storage never held the key */ }
    }
    await window.app.refreshProcessors();
    window.app.saveState('Seed Mixed Redundancy');
    return { pid: proc.id, cards, mxId: mx.id };
}
"""

# What is stored, read back off the client's own project copy (the one
# undo snapshots).
STORED_JS = """(ids) => {
    const p = window.app.project.processors.find(x => x.id === ids.pid);
    return {
        redundancy: !!p.redundancy,
        mixed: p.redundancyMixed === true ? true : (p.redundancyMixed === undefined ? null : p.redundancyMixed),
        cards: p.slots.filter(s => s.card).map(s => ({
            mode: s.card.redundancyMode || null,
            backup: s.card.backupCardId || null,
        })),
    };
}"""

# Each Mixed row: its legend, its chips (lit one), its partner pick, and
# the "Backup for" line where the card is consumed.
ROWS_JS = """(ids) => {
    const pop = document.getElementById('hw-gear-popover');
    return ids.cards.map(id => {
        const chips = pop.querySelector(`[data-lrd-field="processor-card-shape-${id}"]`);
        const pick = pop.querySelector(`[data-lrd-field="processor-card-backup-${id}"]`);
        const fact = pop.querySelector(`[data-lrd-field="processor-card-backupfor-${id}"]`);
        const row = (chips || pick || fact) ? (chips || pick || fact).closest('.hw-pop-red-row') : null;
        const lit = chips ? chips.querySelectorAll('.hw-pop-chip-on') : [];
        return {
            legend: row ? row.querySelector('.hw-pop-red-key').textContent : null,
            modes: chips ? Array.from(chips.children).map(c => c.dataset.mode) : null,
            texts: chips ? Array.from(chips.children).map(c => c.textContent) : null,
            tips: chips ? Array.from(chips.children).map(c => c.title) : null,
            // a chip whose word does not fit its width (ellipsis)
            cut: chips ? Array.from(chips.children)
                .filter(c => c.scrollWidth > c.clientWidth + 1)
                .map(c => c.textContent) : [],
            pickBelow: !!(chips && pick && pick.getBoundingClientRect().top
                          >= chips.getBoundingClientRect().bottom - 1),
            lit: lit.length === 1 ? lit[0].dataset.mode : lit.length,
            pick: pick ? pick.value : null,
            fact: fact ? fact.textContent : null,
        };
    });
}"""

PILLS_JS = """(ids) => {
    const strip = document.querySelector(`[data-lrd-field="processor-name-${ids.pid}"]`);
    const head = strip && strip.closest('.hw-dock-proc-name');
    const pill = head && head.querySelector('.hw-dock-redpill:not(.hw-dock-backuppill)');
    const cardPill = (cid) => {
        const h = document.querySelector(`[data-hwdock="card-${cid}"]`);
        const p = h && h.querySelector('.hw-dock-redpill');
        return p ? p.textContent : null;
    };
    return { proc: pill ? pill.textContent : null, cards: ids.cards.map(cardPill) };
}"""


def open_gear(page, pid):
    assert page.evaluate(OPEN_GEAR_JS, f"proc-{pid}"), 'the processor gear did not open'


def act(page, js, arg):
    assert page.evaluate(js, arg)
    quiet(page)


def pick_partner(page, cid, value):
    page.locator(f'#hw-gear-popover [data-lrd-field="processor-card-backup-{cid}"]') \
        .select_option(value)
    quiet(page)


def test_the_bar_has_mixed_on_a_chassis_and_not_on_a_standalone(page):
    """Four segments behind an H9's ⚙ - Off · Per card · Per port · Mixed -
    and the MX20's three, unchanged."""
    ids = page.evaluate(SEED_JS)
    quiet(page)
    open_gear(page, ids['pid'])
    bar = page.evaluate(BAR_JS, ids['pid'])
    assert bar['levels'] == ['off', 'card', 'port', 'mixed'], bar
    assert bar['texts'] == ['Off', 'Per card', 'Per port', 'Mixed'], bar
    assert bar['lit'] == 'card' and bar['litCount'] == 1, bar
    tip = page.evaluate("""(pid) => document.querySelector(
        `#hw-gear-popover [data-lrd-field="processor-redundancy-${pid}"] [data-level="mixed"]`).title""",
        ids['pid'])
    assert tip.startswith('Mixed: each card picks its own'), tip
    cut = page.evaluate("""(pid) => Array.from(document.querySelector(
        `#hw-gear-popover [data-lrd-field="processor-redundancy-${pid}"]`).children)
        .filter(b => b.scrollWidth > b.clientWidth + 1).map(b => b.textContent)""", ids['pid'])
    assert cut == [], f'segment words cut off: {cut}'
    open_gear(page, ids['mxId'])
    bar = page.evaluate(BAR_JS, ids['mxId'])
    assert bar['levels'] == ['off', 'unit', 'port'], bar
    page.keyboard.press('Escape')
    quiet(page)


def test_mixed_pairs_cards_1_and_2_and_splits_card_3_one_card_at_a_time(page):
    """The owner's H9 built under Mixed: clicking Mixed is one history
    entry and moves no card; card 1 picks card 2 as its partner, card 3
    takes the split - each one request, one undo step, written to its
    own card only - and card 2 reads "Backup for" card 1. The bar stays
    at Mixed throughout, even once card 3 goes back to 1:1 and the cards
    agree; the pills read each card; undo walks it back step by step."""
    ids = page.evaluate(SEED_JS)
    quiet(page)
    c1, c2, c3 = ids['cards']
    open_gear(page, ids['pid'])
    base = page.evaluate(HISTORY_LEN_JS)
    before = page.evaluate(STORED_JS, ids)

    act(page, CLICK_SEG_JS, [ids['pid'], 'mixed'])
    assert page.evaluate(LAST_ACTION_JS) == ['Set Redundancy Mixed']
    assert page.evaluate(HISTORY_LEN_JS) == base + 1
    after = page.evaluate(STORED_JS, ids)
    assert after['cards'] == before['cards'], 'Mixed moved a card'
    assert after['mixed'] is True, after
    open_gear(page, ids['pid'])
    assert page.evaluate(BAR_JS, ids['pid'])['lit'] == 'mixed'
    rows = page.evaluate(ROWS_JS, ids)
    assert [r['legend'] for r in rows] == [
        f'Slot {i} · Card {i}' for i in (1, 2, 3)], rows
    for r in rows:
        assert r['modes'] == ['1to1', 'sequential', 'halves', 'manual'], r
        assert r['texts'] == ['1:1', 'Sequential', 'OPT Split', 'Manual'], r
        assert r['lit'] == '1to1' and r['pick'] == '', r
        assert r['cut'] == [], f'chip words cut off: {r}'
        assert r['pickBelow'], f'the partner pick is not under the chips: {r}'
    # The same tips Per port's chips wear.
    assert rows[0]['tips'][2] == ('Ports 9-16 carry the returns of 1-8. '
                                  'One OPT’s ports, backed by the other’s.'), rows[0]

    # card 1 <- card 2, one request on card 1 alone
    pick_partner(page, c1, c2)
    assert page.evaluate(LAST_ACTION_JS) == ['Change Backup Unit']
    assert page.evaluate(HISTORY_LEN_JS) == base + 2
    st = page.evaluate(STORED_JS, ids)
    assert st['cards'] == [{'mode': None, 'backup': c2},
                           {'mode': None, 'backup': None},
                           {'mode': None, 'backup': None}], st
    open_gear(page, ids['pid'])
    rows = page.evaluate(ROWS_JS, ids)
    assert rows[0]['pick'] == c2, rows
    assert rows[1]['fact'] == 'Backup for Slot 1 · Card 1', rows
    assert rows[1]['modes'] is None and rows[1]['pick'] is None, (
        'a consumed card still offers controls', rows)

    # card 3 -> the split, one request on card 3 alone
    act(page, CLICK_CHIP_JS, [c3, 'halves'])
    assert page.evaluate(LAST_ACTION_JS) == ['Change Redundancy Mode']
    assert page.evaluate(HISTORY_LEN_JS) == base + 3
    st = page.evaluate(STORED_JS, ids)
    assert st['cards'] == [{'mode': None, 'backup': c2},
                           {'mode': None, 'backup': None},
                           {'mode': 'halves', 'backup': None}], st
    open_gear(page, ids['pid'])
    assert page.evaluate(BAR_JS, ids['pid'])['lit'] == 'mixed'
    rows = page.evaluate(ROWS_JS, ids)
    assert rows[2]['lit'] == 'halves' and rows[2]['pick'] is None, rows

    # The tray reads each card on its own row; the header says Mixed.
    pills = page.evaluate(PILLS_JS, ids)
    assert pills == {'proc': 'R mixed',
                     'cards': ['R 1:1 → Card 2 in SR', None, 'R OPT split']}, pills

    # Card 3 back to 1:1: the cards now agree, the bar stays at Mixed.
    act(page, CLICK_CHIP_JS, [c3, '1to1'])
    st = page.evaluate(STORED_JS, ids)
    assert st['cards'][2] == {'mode': None, 'backup': None} and st['mixed'] is True, st
    open_gear(page, ids['pid'])
    assert page.evaluate(BAR_JS, ids['pid'])['lit'] == 'mixed'
    # A press on the lit Mixed segment is a no-op.
    hist = page.evaluate(HISTORY_LEN_JS)
    act(page, CLICK_SEG_JS, [ids['pid'], 'mixed'])
    assert page.evaluate(HISTORY_LEN_JS) == hist

    # Undo walks the row writes back one at a time.
    page.keyboard.press('Escape')
    quiet(page)
    page.evaluate("() => window.app.undo()")
    quiet(page)
    assert page.evaluate(STORED_JS, ids)['cards'][2]['mode'] == 'halves'
    page.evaluate("() => window.app.undo()")
    quiet(page)
    st = page.evaluate(STORED_JS, ids)
    assert st['cards'][2]['mode'] is None and st['cards'][0]['backup'] == c2, st
    page.evaluate("() => window.app.undo()")
    quiet(page)
    st = page.evaluate(STORED_JS, ids)
    assert st['cards'][0]['backup'] is None and st['mixed'] is True, st
    page.evaluate("() => window.app.undo()")
    quiet(page)
    assert page.evaluate(STORED_JS, ids)['mixed'] is None
    open_gear(page, ids['pid'])
    assert page.evaluate(BAR_JS, ids['pid'])['lit'] == 'card'
    page.evaluate("() => window.app.redo()")
    quiet(page)
    open_gear(page, ids['pid'])
    assert page.evaluate(BAR_JS, ids['pid'])['lit'] == 'mixed'
    page.keyboard.press('Escape')
    quiet(page)


def test_per_card_and_per_port_from_mixed_convert_every_card(page):
    """From Mixed (card 1 <- card 2, card 3 at the split), Per port sets
    every card sequential in one write and Per card every card 1:1 in one
    write - the stored partner left underneath - and either lets go of
    Mixed. Mixed from there moves no card again."""
    ids = page.evaluate(SEED_JS)
    quiet(page)
    c1, c2, c3 = ids['cards']
    open_gear(page, ids['pid'])
    act(page, CLICK_SEG_JS, [ids['pid'], 'mixed'])
    open_gear(page, ids['pid'])
    pick_partner(page, c1, c2)
    open_gear(page, ids['pid'])
    act(page, CLICK_CHIP_JS, [c3, 'halves'])
    open_gear(page, ids['pid'])
    base = page.evaluate(HISTORY_LEN_JS)

    act(page, CLICK_SEG_JS, [ids['pid'], 'port'])
    assert page.evaluate(LAST_ACTION_JS) == ['Set Redundancy Per Port']
    assert page.evaluate(HISTORY_LEN_JS) == base + 1
    st = page.evaluate(STORED_JS, ids)
    assert [c['mode'] for c in st['cards']] == ['sequential'] * 3, st
    assert st['mixed'] is None, st
    open_gear(page, ids['pid'])
    assert page.evaluate(BAR_JS, ids['pid'])['lit'] == 'port'

    act(page, CLICK_SEG_JS, [ids['pid'], 'mixed'])
    st = page.evaluate(STORED_JS, ids)
    assert [c['mode'] for c in st['cards']] == ['sequential'] * 3, st
    assert st['mixed'] is True
    open_gear(page, ids['pid'])
    assert page.evaluate(BAR_JS, ids['pid'])['lit'] == 'mixed'
    # Per port from Mixed with every card already in a port shape lets go
    # of Mixed and leaves the shapes.
    act(page, CLICK_SEG_JS, [ids['pid'], 'port'])
    st = page.evaluate(STORED_JS, ids)
    assert [c['mode'] for c in st['cards']] == ['sequential'] * 3 and st['mixed'] is None, st

    open_gear(page, ids['pid'])
    act(page, CLICK_SEG_JS, [ids['pid'], 'mixed'])
    open_gear(page, ids['pid'])
    act(page, CLICK_CHIP_JS, [c3, 'halves'])
    open_gear(page, ids['pid'])
    act(page, CLICK_SEG_JS, [ids['pid'], 'card'])
    assert page.evaluate(LAST_ACTION_JS) == ['Set Redundancy Per Card']
    st = page.evaluate(STORED_JS, ids)
    assert [c['mode'] for c in st['cards']] == [None] * 3, st
    assert st['cards'][0]['backup'] == c2 and st['mixed'] is None, st
    open_gear(page, ids['pid'])
    assert page.evaluate(BAR_JS, ids['pid'])['lit'] == 'card'
    page.keyboard.press('Escape')
    quiet(page)


def test_a_mixed_chassis_with_no_pick_reads_mixed_from_its_cards(page):
    """A chassis whose cards disagree - the shape an older show saved -
    lights Mixed with no pick stored, its rows each showing their own
    card's kind; Off from there is one write."""
    ids = page.evaluate(SEED_JS)
    quiet(page)
    c1, c2, c3 = ids['cards']
    page.evaluate("""async ([pid, c1, c2, c3]) => {
        const send = (url, body) => fetch(url, { method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body) });
        await send(`/api/processors/${pid}/cards/${c1}`, { backupCardId: c2 });
        await send(`/api/processors/${pid}/cards/${c3}`, { redundancyMode: 'sequential' });
        await window.app.refreshProcessors();
    }""", [ids['pid'], c1, c2, c3])
    quiet(page)
    assert page.evaluate(STORED_JS, ids)['mixed'] is None
    open_gear(page, ids['pid'])
    assert page.evaluate(BAR_JS, ids['pid'])['lit'] == 'mixed'
    rows = page.evaluate(ROWS_JS, ids)
    assert rows[0]['lit'] == '1to1' and rows[0]['pick'] == c2, rows
    assert rows[1]['fact'] == 'Backup for Slot 1 · Card 1', rows
    assert rows[2]['lit'] == 'sequential', rows
    pills = page.evaluate(PILLS_JS, ids)
    assert pills['proc'] == 'R mixed' and pills['cards'][2] == 'R seq', pills
    act(page, CLICK_SEG_JS, [ids['pid'], 'off'])
    assert page.evaluate(LAST_ACTION_JS) == ['Toggle Redundancy']
    st = page.evaluate(STORED_JS, ids)
    assert st['redundancy'] is False and st['cards'][2]['mode'] == 'sequential', st
    page.keyboard.press('Escape')
    quiet(page)


# ── downstream: the binder and the pull sheet on a mixed chassis ─────────
#
# test_binder_tables' own backup show is the owner's case already: one H9,
# card 1's box SR A backed 1:1 by card 2's box SR B, card 3 (SOLO) in a
# port shape of its own. Seeded as it stands (halves) and with card 3 at
# sequential.

PULL_JS = """async () => {
    const app = window.app;
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app._circuitTailCache = null;
    const list = JSON.parse(JSON.stringify(app.buildPullList()));
    const proc = app._processorsResolved[0];
    const cards = proc.slots.filter(s => s.card).map(s => s.card);
    const ports = (name) => {
        const layer = app.project.layers.find(l => l.name === name);
        return ((list.byScreen[String(layer.id)] || {}).ports || []);
    };
    return {
        level: app._procRedundancyLevel(proc),
        mixedPick: proc.redundancyMixed,
        cards: cards.map(c => c.id),
        shapes: cards.map(c => c.redundancyShape && c.redundancyShape.mode),
        main: ports('MAIN').map(p => p.backup ? p.backup.label : null),
        solo: ports('SOLO').map(p => p.backup ? p.backup.label : null),
        soloBacked: ports('SOLO').map(p => {
            const layer = app.project.layers.find(l => l.name === 'SOLO');
            const asg = (app._assignment.screens || []).find(s => String(s.layerId) === String(layer.id));
            const placed = asg && asg.ports.find(q => q.number === p.num);
            const bb = placed && app._pullBackedBy(placed.cardId, placed.port);
            return placed ? [placed.port, bb ? bb.port : null, bb ? bb.cardId === placed.cardId : null] : null;
        }),
    };
}"""


@pytest.fixture(scope="module")
def mixed_show(e2e_server, pw_browser):
    """The binder's backup show at halves and at sequential: its pull list
    and every binder sheet, each rendered once."""
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    out = {}
    for third in ('halves', 'sequential'):
        seed = SEED_BACKUP_JS.replace("{redundancyMode: 'halves'}",
                                      "{redundancyMode: '%s'}" % third)
        assert seed.count(third) >= 1
        project = pg.evaluate(seed)
        pull = pg.evaluate(PULL_JS)
        sheets = pg.evaluate(SHEETS_JS, [project, OPTS])
        out[third] = {'pull': pull,
                      'pages': {p['title']: p for p in sheets['pages']}}
    assert not errors, errors[:3]
    yield out
    context.close()


@pytest.mark.parametrize('third', ['halves', 'sequential'])
def test_the_mixed_show_reads_mixed_and_each_card_its_own_shape(mixed_show, third):
    pull = mixed_show[third]['pull']
    assert pull['level'] == 'mixed', pull
    assert pull['mixedPick'] is False, 'an older-shaped show grew a pick'
    assert pull['shapes'] == ['1to1', '1to1', third], pull


@pytest.mark.parametrize('third', ['halves', 'sequential'])
def test_the_binder_ports_tables_read_each_card(mixed_show, third):
    """MAIN, on card 1: ONE section, SR A over the primary half and SR B -
    card 2, its 1:1 partner - over the backup half. SOLO, on card 3: one
    section, no second unit, every row's return on SOLO itself."""
    pages = mixed_show[third]['pages']
    main = _ports_table(pages['MAIN - Data - Front View'])
    assert len(main) == 1, main
    assert main[0]['band'][0].startswith('CVT4K-S SR A · '), main
    assert main[0]['backup'][0].startswith('CVT4K-S SR B · '), main
    rows = _all_rows(main)
    assert [r['B PORT'] for r in rows] == [f'SR B-{i}' for i in range(1, 5)], rows
    solo = _ports_table(pages['SOLO - Data - Front View'])
    assert len(solo) == 1 and solo[0]['backup'] == [], solo
    rows = _all_rows(solo)
    assert rows and all('SOLO' in r.get('B OUTPUT', '') for r in rows), rows


@pytest.mark.parametrize('third', ['halves', 'sequential'])
def test_the_binder_names_mixed_and_each_cards_backup(mixed_show, third):
    """The processor's Redundancy line says Mixed; the Cards table reads
    per card - card 1 its partner, card 2 whose backup it is, card 3 its
    own shape (never a stale partner) - each in the app's own words: the
    cards nobody named by their slots (Card 1, Card 2), the shape by the
    chip's word, never the stored id ("halves", "sequential")."""
    texts = [o['t'] for p in mixed_show[third]['pages'].values() for o in p['texts']]
    assert 'Mixed' in texts, 'no sheet says the processor is Mixed'
    assert 'backs up Card 1' in texts, 'card 2 does not say whose backup it is'
    assert any('backed up by Card 2' in t for t in texts), 'card 1 does not name its partner'
    # card 3 is an H_20xRJ45, copper only: its split names no OPT
    word = {'halves': 'Split', 'sequential': 'Sequential'}[third]
    assert word in texts, f'card 3 does not read {word}'
    assert third not in texts, f'a sheet still prints the stored id {third}'
    assert not any(t.startswith('slot ') for t in texts), [t for t in texts if 'slot' in t]


@pytest.mark.parametrize('third', ['halves', 'sequential'])
def test_the_pull_sheet_walks_each_backup_end(mixed_show, third):
    """Every MAIN port's backup end is walked (on card 2's box), and every
    SOLO port's comes back on card 3 itself - port N on N + half in
    halves, on N + 1 in sequential."""
    pull = mixed_show[third]['pull']
    assert pull['main'] and all(pull['main']), pull['main']
    assert pull['solo'] and all(pull['solo']), pull['solo']
    backed = pull['soloBacked']
    assert backed and all(b and b[2] for b in backed), backed
    if third == 'halves':
        assert all(b[1] == b[0] + 10 for b in backed), backed
    else:
        assert all(b[0] % 2 == 1 and b[1] == b[0] + 1 for b in backed), backed


# ── A partner pick with nothing to pick (QA, 1.6.0 beta 5) ───────────────
#
# Card 3's "backed up by..." opened on an empty list with no word why:
# card 1 is backed up by card 2, so neither is free to back card 3 up and
# there is no other card. The empty pick is not drawn; the reason is said
# in its place.

SEED_PAIRED_JS = """
async (n) => {
    const state = await (await fetch('/api/processors')).json();
    for (const p of state.processors) {
        await fetch(`/api/processors/${p.id}`, { method: 'DELETE' });
    }
    const send = (url, method, body) => fetch(url, {
        method, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    }).then(r => r.json());
    let st = await send('/api/processors', 'POST',
                        { deviceId: 'novastar-h9', name: 'SR' });
    const proc = st.resolved[st.resolved.length - 1];
    for (let i = 0; i < n; i++) {
        st = await send(`/api/processors/${proc.id}/slots/${i}`, 'PUT',
                        { deviceId: 'novastar-card-h-16xrj45-2xfiber' });
    }
    const cards = st.resolved.find(p => p.id === proc.id)
        .slots.filter(s => s.card).map(s => s.card.id);
    await send(`/api/processors/${proc.id}`, 'PUT', { redundancy: true });
    if (n > 1) {
        await send(`/api/processors/${proc.id}/cards/${cards[0]}`, 'PUT',
                   { backupCardId: cards[1] });
    }
    await window.app.refreshProcessors();
    window.app.saveState('Seed Paired Cards');
    return { pid: proc.id, cards };
}
"""

NO_PARTNER_JS = """(cid) => {
    const pop = document.getElementById('hw-gear-popover');
    const pick = pop.querySelector(`[data-lrd-field="processor-card-backup-${cid}"]`);
    const none = pop.querySelector(`[data-lrd-field="processor-card-nopartner-${cid}"]`);
    return {
        pick: pick ? Array.from(pick.options).map(o => o.textContent) : null,
        text: none ? none.textContent : null,
        title: none ? none.title : null,
    };
}"""


def test_a_card_with_no_free_partner_says_why_instead_of_an_empty_pick(page):
    ids = page.evaluate(SEED_PAIRED_JS, 3)
    quiet(page)
    open_gear(page, ids['pid'])
    first, _second, third = ids['cards']
    got = page.evaluate(NO_PARTNER_JS, third)
    assert got['pick'] is None, f'an empty partner pick is drawn: {got}'
    assert got['text'] == 'no card free to back it up', got
    assert got['title'].startswith('Every other card already backs one up'), got
    # card 1 keeps its pick, its partner shown
    kept = page.evaluate(NO_PARTNER_JS, first)
    assert kept['pick'] and len(kept['pick']) > 1 and kept['text'] is None, kept


def test_a_lone_card_says_there_is_no_other_card(page):
    ids = page.evaluate(SEED_PAIRED_JS, 1)
    quiet(page)
    open_gear(page, ids['pid'])
    got = page.evaluate(NO_PARTNER_JS, ids['cards'][0])
    assert got['pick'] is None, got
    assert got['text'] == 'no other card to back it up', got
