"""A folded box's cable sheet lists its backup ports' cables too.

The owner, 2026-11-04, on the Data tray: "oh you can, it is just hidden.
When you click the extension menu when the boxes are collapsed it only shows
the primary." A loop strip folded carries one ≡, its primary's, and its
sheet listed the primary's sockets only: the backup cables (the far box of
an XD loop, a NovaStar 1:1 partner, a port-by-port backup box) were typed
only from the rows' own ≡, which the fold hides. The same held for a card
folded over the copy OPT box backing up its own ports.

So, for every redundancy shape with backup copper ports:

  * the ≡ sheet folded lists the same rows, labels and keys as the open
    section's sheets together
  * a length typed in a folded sheet's backup row is stored on the backup
    box's own entry, survives a re-render, and reads the same in the open
    sheet and on the pull list

The processor's own ≡ (owner, same day: "when the whole processor is
collapsed we should have an extension drop down that opens all boxes
connected in the same way") lists every section's folded list in tray order,
its fields keyed apart from the boxes' own, each length the same stored entry.

Synthetic hardware only, one scratch project per shape.
"""

import os
import sys

import pytest

from conftest import settled  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


DIALOGS = ('save-file', 'open-file', 'select-directory')

FETCH_COUNT_JS = """(() => {
    const orig = window.fetch;
    window.__lrdFetches = 0;
    window.fetch = function (...args) {
        window.__lrdFetches++;
        const sent = orig.apply(this, args);
        const done = () => setTimeout(() => { window.__lrdFetches--; }, 0);
        sent.then(r => r.clone().text().then(done, done), done);
        return sent;
    };
})()"""

QUIET_JS = """() => {
    const app = window.app;
    const idle = window.__lrdFetches === 0 && !app._saveStateTimer
        && !app._dockMasonryRaf;
    window.__lrdQuiet = idle ? (window.__lrdQuiet || 0) + 1 : 0;
    return window.__lrdQuiet >= 2;
}"""

# One processor per shape, a wall placed on the primary's first ports, and
# the backup end of the wall's port 1: the entry its backup cable is kept
# under (backupCableKey) and the sheet field that types it.
SEED_JS = """async (shape) => {
    const app = window.app;
    const send = (url, method, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) })
        .then(r => r.json());
    try {
        for (let i = localStorage.length - 1; i >= 0; i--) {
            const k = localStorage.key(i);
            if (/^lrd_data_cable_sheet_|^ledRasterPanelCollapsed_hwdock-/.test(k)) {
                localStorage.removeItem(k);
            }
        }
    } catch (_) { /* no storage */ }
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await send('/api/project', 'PUT', proj);
    await send('/api/layer/add', 'POST', { name: 'BIG', columns: 4, rows: 2,
        cabinet_width: 500, cabinet_height: 500 });
    const add = async (deviceId) => {
        const st = await send('/api/processors', 'POST', { deviceId });
        return st.resolved[st.resolved.length - 1];
    };
    const box = (p, c, body) => send(`/api/processors/${p}/cards/${c}/cvts`,
                                     'POST', body);
    let proc;
    if (shape === 'xd-loop') {
        proc = await add('brompton-sx40');
        await send(`/api/processors/${proc.id}`, 'PUT', { redundancy: true });
    } else if (shape === 'novastar-pair') {
        proc = await add('novastar-mx40-pro');
        const c = proc.slots[0].card.id;
        await send(`/api/processors/${proc.id}/cards/${c}`, 'PUT', { mode: '20-port' });
        await box(proc.id, c, { deviceId: 'novastar-cvt10' });
    } else if (shape === 'novastar-pairs') {
        proc = await add('novastar-mx40-pro');
        const c = proc.slots[0].card.id;
        await send(`/api/processors/${proc.id}/cards/${c}`, 'PUT', { mode: '20-port' });
        await box(proc.id, c, { deviceId: 'novastar-cvt10' });
        await box(proc.id, c, { deviceId: 'novastar-cvt10' });
    } else if (shape === 'no-boxes') {
        proc = await add('novastar-vx1000');
    } else if (shape === 'straddle') {
        proc = await add('novastar-vx1000');
        await box(proc.id, proc.slots[0].card.id,
                  { deviceId: 'novastar-cvt4k-s', pair: false });
    } else if (shape === 'port-by-port') {
        proc = await add('novastar-novapro-uhd-jr');
        const c = proc.slots[0].card.id;
        for (const d of ['novastar-cvt10', 'novastar-cvt10', 'novastar-cvt4k-s']) {
            await box(proc.id, c, { deviceId: d, pair: false });
        }
    } else if (shape === 'own-ports') {
        proc = await add('novastar-novapro-uhd-jr');
        await box(proc.id, proc.slots[0].card.id,
                  { deviceId: 'novastar-cvt4k-s', trunk: 2 });
    }
    await app.refreshProcessors();
    const card = app._processorsResolved.find(p => p.id === proc.id)
        .slots[0].card;
    const cvts = card.cvts || [];
    let sec, boxId = null, ports;
    if (shape === 'own-ports' || shape === 'no-boxes') {
        sec = `hwdock-card-${card.id}`;
        ports = card.ports.filter(p => !p.cvtId);
    } else {
        const near = cvts.find(b => cvts.some(c => c.backupOf === b.id))
            || cvts.find(b => app.boxStraddles(b))
            || cvts.find(b => (b.backedUpBy || []).length);
        sec = `hwdock-box-${near.id}`;
        boxId = near.id;
        ports = app.boxMainPorts(near);
    }
    app.project = await send('/api/project', 'GET');
    const wall = app.project.layers.find(l => l.name === 'BIG');
    const nums = ports.map(p => p.number);
    const place = { layerId: String(wall.id), cardId: card.id,
        firstPort: Math.min(...nums), lastPort: Math.max(...nums),
        screens: [{ layerId: String(wall.id), name: 'BIG',
                    ports: app.getLayerPortsRequired(wall) }] };
    if (boxId) place.boxId = boxId;
    await app._assignmentRequest('/api/port-assignments/place-overflow',
                                 'POST', place);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    const pin = app._screenPortPin(wall, 1);
    // the port's backup end, or (a processor with no backup) the port
    const bb = pin && (app._pullBackedBy(pin.cardId, pin.port)
        || (shape === 'no-boxes' ? { cardId: pin.cardId, port: pin.port } : null));
    if (!bb) return { error: 'no backup end', pin, shape };
    const ownerId = bb.cvtId || bb.cardId;
    const storeKey = app.backupCableKey(bb) || String(bb.port);
    app.renderHardwareDock();
    return {
        sec, proc: proc.id, card: card.id,
        ownerKind: bb.cvtId ? 'cvt' : 'card', ownerId, storeKey,
        field: `data-cable-ft-${ownerId}-${storeKey}`,
    };
}"""

CLEAR_SHEETS_JS = """() => {
    try {
        for (let i = localStorage.length - 1; i >= 0; i--) {
            const k = localStorage.key(i);
            if (/^lrd_data_cable_sheet_/.test(k)) localStorage.removeItem(k);
        }
    } catch (_) { /* no storage */ }
    window.app.renderHardwareDock();
}"""

FOLDED_JS = """(sec) => {
    const s = document.querySelector(`[data-lrd-sec-id="${sec}"]`);
    return !!s && s.classList.contains('lrd-sec-collapsed');
}"""

# Every cable row a user can see in the section's sheets: its length field's
# key and its port cell, in order.
ROWS_JS = """(sec) => {
    const s = document.querySelector(`[data-lrd-sec-id="${sec}"]`);
    const shown = (el) => el.getClientRects().length > 0;
    return [...s.querySelectorAll('.hw-dock-cablesheet input.hw-dock-cable-ft')]
        .filter(f => shown(f) && /^data-cable-ft-/.test(f.dataset.lrdField))
        .map(f => [f.dataset.lrdField, f.closest('tr').children[1].textContent]);
}"""

# The ≡ buttons a user can see in the section that are not flipped yet.
CLOSED_BUTTONS_JS = """(sec) => {
    const s = document.querySelector(`[data-lrd-sec-id="${sec}"]`);
    return [...s.querySelectorAll('.hw-dock-cablebtn-data')]
        .filter(b => b.getClientRects().length > 0
                && !b.classList.contains('hw-dock-cablebtn-on'))
        .map(b => b.dataset.lrdField);
}"""

STORED_JS = """([kind, id, key]) => {
    const owner = window.app._dataCableOwner(kind, id);
    const rec = owner && (owner.rec.portCables || {})[key];
    return rec ? rec.ft : null;
}"""

PULL_JS = """() => {
    const list = window.app.buildPullList();
    const scr = Object.values(list.byScreen || {}).find(s => s.name === 'BIG');
    const p = scr && scr.ports[0];
    return p && p.backup ? p.backup.cable : null;
}"""

SHAPES = ['xd-loop', 'novastar-pair', 'straddle', 'port-by-port', 'own-ports']


def landed(page):
    page.evaluate("() => { window.__lrdQuiet = 0; }")
    page.wait_for_function(QUIET_JS)


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    for name in DIALOGS:
        context.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body='{"ok": false, "cancelled": true, "unavailable": false}'))
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete"
                         " === true && window.app._socketConnects >= 1")
    landed(pg)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_function(
        "() => window.canvasRenderer.viewMode === 'data-flow'")
    landed(pg)
    yield pg, errors
    context.close()


def set_fold(page, sec, folded):
    """Fold or open a section with its own arrow, the user's gesture."""
    if page.evaluate(FOLDED_JS, sec) != folded:
        page.locator(f'[data-lrd-sec-id="{sec}"] > .lrd-sec-head '
                     '.lrd-sec-arrow').click()
        landed(page)
    assert page.evaluate(FOLDED_JS, sec) == folded


def folded_rows(page, sec):
    """Fold the section, press the one ≡ its header shows, read the sheet."""
    page.evaluate(CLEAR_SHEETS_JS)
    landed(page)
    set_fold(page, sec, True)
    shut = page.evaluate(CLOSED_BUTTONS_JS, sec)
    assert len(shut) == 1, f'a folded section shows one ≡: {shut}'
    page.locator(f'[data-lrd-sec-id="{sec}"] [data-lrd-field="{shut[0]}"]').click()
    landed(page)
    assert page.evaluate(FOLDED_JS, sec), 'the ≡ unfolded the section'
    return page.evaluate(ROWS_JS, sec)


def open_rows(page, sec):
    """Open the section and press every ≡ in it, read the sheets."""
    page.evaluate(CLEAR_SHEETS_JS)
    landed(page)
    set_fold(page, sec, False)
    for _ in range(8):
        shut = page.evaluate(CLOSED_BUTTONS_JS, sec)
        if not shut:
            break
        page.locator(f'[data-lrd-sec-id="{sec}"] '
                     f'[data-lrd-field="{shut[0]}"]').click()
        landed(page)
    assert not page.evaluate(CLOSED_BUTTONS_JS, sec)
    return page.evaluate(ROWS_JS, sec)


@pytest.mark.parametrize('shape', SHAPES)
def test_a_folded_sheet_lists_the_backup_rows_the_open_one_does(page, shape):
    pg, errors = page
    seed = pg.evaluate(SEED_JS, shape)
    assert 'error' not in seed, seed
    landed(pg)
    sec = seed['sec']

    opened = open_rows(pg, sec)
    keys = [k for k, _ in opened]
    assert seed['field'] in keys, (
        f'the open section has no row for the backup cable: {opened}')
    assert len(keys) == len(set(keys)), opened

    folded = folded_rows(pg, sec)
    assert folded == opened, (
        f'folded, the ≡ sheet lists other rows than open:\n'
        f'folded {folded}\nopen   {opened}')

    # A length typed in the folded sheet's backup row is that backup's.
    field = pg.locator(f'[data-lrd-sec-id="{sec}"] '
                       f'[data-lrd-field="{seed["field"]}"]')
    field.click()
    field.fill('40')
    pg.keyboard.press('Enter')
    landed(pg)
    stored = settled(pg, lambda: pg.evaluate(
        STORED_JS, [seed['ownerKind'], seed['ownerId'], seed['storeKey']]),
        lambda v: v == 40)
    assert stored == 40, stored
    pg.evaluate("() => window.app.renderHardwareDock()")
    landed(pg)
    assert pg.evaluate(FOLDED_JS, sec), 'the edit unfolded the section'
    assert pg.locator(f'[data-lrd-sec-id="{sec}"] '
                      f'[data-lrd-field="{seed["field"]}"]').input_value() == '40'
    pull = pg.evaluate(PULL_JS)
    assert pull and pull.startswith("40'"), pull
    # ...and the open section's sheet reads the same length on that row
    open_rows(pg, sec)
    assert pg.locator(f'[data-lrd-sec-id="{sec}"] '
                      f'[data-lrd-field="{seed["field"]}"]').input_value() == '40'
    pg.evaluate(CLEAR_SHEETS_JS)
    landed(pg)
    assert not errors, errors


# ── the processor's ≡: every box's cable list at once ───────────────────
#
# The owner, 2026-11-04: "when the whole processor is collapsed we should
# have an extension drop down that opens all boxes connected in the same
# way". The processor's strip has a ≡ of its own; its list is each tray
# section's own folded ≡ list, in tray order, under the section's name.

# The tray's sections of one processor that have a ≡ of their own, in tray
# order: each card's own ports first where it has any, then its box strips.
SECTIONS_JS = """(procId) => {
    const app = window.app;
    const proc = app._processorsResolved.find(p => p.id === procId);
    const out = [];
    proc.slots.forEach(slot => {
        const card = slot.card;
        if (!card) return;
        if (card.ports.some(p => !p.cvtId)) out.push(`hwdock-card-${card.id}`);
        const unit = document.querySelector(`[data-lrd-sec-id="hwdock-card-${card.id}"]`);
        unit.querySelectorAll('[data-lrd-sec-id^="hwdock-box-"]').forEach(
            s => out.push(s.dataset.lrdSecId));
    });
    return out;
}"""

PROC_ROWS_JS = """(procId) => {
    const list = document.querySelector(`[data-lrd-proc-sheet="${procId}"]`);
    if (!list) return null;
    const ns = `proclist-${procId}-`;
    const shown = (el) => el.getClientRects().length > 0;
    return {
        heads: [...list.querySelectorAll('.hw-dock-proc-sheet-head')]
            .map(h => h.textContent),
        rows: [...list.querySelectorAll('input.hw-dock-cable-ft')]
            .filter(f => shown(f)
                    && f.dataset.lrdField.startsWith(ns + 'data-cable-ft-'))
            .map(f => [f.dataset.lrdField.slice(ns.length),
                       f.closest('tr').children[1].textContent]),
        // every key in the list is its own, never another field's
        clash: [...list.querySelectorAll('[data-lrd-field]')]
            .filter(f => !f.dataset.lrdField.startsWith(ns)).length,
    };
}"""

# How the tray names each section, for the list's headings: a loop strip
# by its model and its two ends, a lone box by its name, a card by its
# header's model text.
TRAY_NAMES_JS = """(secs) => secs.map(sec => {
    const app = window.app;
    const s = document.querySelector(`[data-lrd-sec-id="${sec}"]`);
    const head = s.querySelector(':scope > .lrd-sec-head');
    if (sec.startsWith('hwdock-card-')) {
        const m = head.querySelector('.hw-dock-unit-name');
        return m ? m.textContent : null;
    }
    const box = app._dockFindCvt(sec.slice('hwdock-box-'.length)).cvt;
    const names = head.querySelector('.hw-dock-loop-names');
    return names ? `${box.deviceName} ${names.textContent}` : app._dockBoxLabel(box);
})"""

CARD_OF_JS = """(sec) => document.querySelector(`[data-lrd-sec-id="${sec}"]`)
    .closest('[data-lrd-sec-id^="hwdock-card-"]').dataset.lrdSecId"""

PULL_PRIMARY_JS = """() => {
    const list = window.app.buildPullList();
    const scr = Object.values(list.byScreen || {}).find(s => s.name === 'BIG');
    return scr && scr.ports[0] ? scr.ports[0].cable : null;
}"""


def proc_rows(page, proc):
    """Press the processor's ≡ (every sheet closed first), read its list."""
    page.evaluate(CLEAR_SHEETS_JS)
    landed(page)
    btn = page.locator(f'[data-lrd-field="data-cable-sheet-{proc}"]')
    assert 'hw-dock-cablebtn-proc' in btn.get_attribute('class')
    btn.click()
    landed(page)
    assert 'hw-dock-cablebtn-on' in btn.get_attribute('class')
    return page.evaluate(PROC_ROWS_JS, proc)


def fold_all(page, secs, folded):
    """Fold or open every section; the boxes before their card on the way
    down, the card first on the way up, so no arrow is hidden."""
    boxes = [s for s in secs if s.startswith('hwdock-box-')]
    cards = list(dict.fromkeys(
        [page.evaluate(CARD_OF_JS, s) for s in boxes]
        + [s for s in secs if s.startswith('hwdock-card-')]))
    for sec in (boxes + cards if folded else cards + boxes):
        set_fold(page, sec, folded)


@pytest.mark.parametrize('shape', ['xd-loop', 'novastar-pairs', 'no-boxes'])
def test_the_processor_list_is_every_boxs_list_in_tray_order(page, shape):
    pg, errors = page
    seed = pg.evaluate(SEED_JS, shape)
    assert 'error' not in seed, seed
    landed(pg)
    proc = seed['proc']
    secs = pg.evaluate(SECTIONS_JS, proc)
    boxes = [s for s in secs if s.startswith('hwdock-box-')]
    if shape == 'xd-loop':
        assert len(boxes) == 2, secs
    elif shape == 'novastar-pairs':
        assert boxes, secs
    else:
        assert secs == [f'hwdock-card-{seed["card"]}'], secs

    # Each section's own ≡ list, folded, in tray order.
    fold_all(pg, secs, False)
    names = pg.evaluate(TRAY_NAMES_JS, secs)
    union = []
    for sec in boxes:
        union.extend(folded_rows(pg, sec))
    fold_all(pg, secs, False)
    for sec in reversed([s for s in secs if s.startswith('hwdock-card-')]):
        union[0:0] = folded_rows(pg, sec)
    assert seed['field'] in [k for k, _ in union], union

    # The processor's list with everything open, then everything folded.
    fold_all(pg, secs, False)
    got = proc_rows(pg, proc)
    assert got['rows'] == union, (
        'the processor list is not the boxes\' lists in order:\n'
        f'list  {got["rows"]}\nboxes {union}')
    assert got['clash'] == 0, got
    assert got['heads'] == names, (got['heads'], names)
    if shape == 'xd-loop':
        assert all(h.startswith('XD ') and '↔' in h for h in got['heads']), got
    fold_all(pg, secs, True)
    shut = proc_rows(pg, proc)
    assert shut['rows'] == union and shut['heads'] == names, shut

    # A length typed in the processor list is the box list's entry too.
    field = pg.locator(f'[data-lrd-proc-sheet="{proc}"] '
                       f'[data-lrd-field="proclist-{proc}-{seed["field"]}"]')
    field.click()
    field.fill('40')
    pg.keyboard.press('Enter')
    landed(pg)
    stored = settled(pg, lambda: pg.evaluate(
        STORED_JS, [seed['ownerKind'], seed['ownerId'], seed['storeKey']]),
        lambda v: v == 40)
    assert stored == 40, stored
    pg.evaluate("() => window.app.renderHardwareDock()")
    landed(pg)
    assert field.input_value() == '40'
    pull = pg.evaluate(PULL_PRIMARY_JS if shape == 'no-boxes' else PULL_JS)
    assert pull and pull.startswith("40'"), pull
    # the processor's ≡ again closes the list
    pg.locator(f'[data-lrd-field="data-cable-sheet-{proc}"]').click()
    landed(pg)
    assert pg.evaluate(PROC_ROWS_JS, proc) is None
    # ...and the section's own list reads the length on the same row
    fold_all(pg, secs, False)
    owner_sec = None
    for sec in boxes + [s for s in secs if s.startswith('hwdock-card-')]:
        rows = folded_rows(pg, sec)
        fold_all(pg, secs, False)
        if seed['field'] in [k for k, _ in rows]:
            owner_sec = sec
            break
    assert owner_sec, 'no section list shows the typed row'
    folded_rows(pg, owner_sec)
    assert pg.locator(f'[data-lrd-sec-id="{owner_sec}"] '
                      f'[data-lrd-field="{seed["field"]}"]').input_value() == '40'
    pg.evaluate(CLEAR_SHEETS_JS)
    landed(pg)
    fold_all(pg, secs, False)
    assert not errors, errors
