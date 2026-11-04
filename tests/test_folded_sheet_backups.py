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
    if (shape === 'own-ports') {
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
    const bb = pin && app._pullBackedBy(pin.cardId, pin.port);
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
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
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
