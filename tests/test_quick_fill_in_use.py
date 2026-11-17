"""Quick fill reaches every backup and skips what is empty.

The owner, 2026-11-16: "quick fill lengths doesnt work on backups when
using looped backup XD's and the processor is minimized. so we need to
check all instances of this and fix it. also when i fill it puts lengths
on empty ports. this also happens on power and should not fill empty ones"

So, for the data cable sheets, in every redundancy shape that has copper
backups and in every tray state that offers a quick fill:

  * all 100' writes a length on every socket a screen's port is on and on
    every socket carrying that port's backup, whichever sheet lists it:
    the box's own, a folded strip's or card's one sheet, or the
    processor's list with the tray open or minimized
  * a socket with nothing on it takes no length
  * one press is one undo step, even when it wrote two boxes
  * the pull sheet reads the length on every port and every backup

and for the power cable sheet, all 10' writes only the circuits that feed
panels: a hand-drawn circuit whose cabinets are all blanked or removed
takes no cable, and none still clears every circuit.

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

# One processor per shape and a wall placed on the primary's first ports,
# leaving the rest of the sockets empty.
#   xd-loop        SX40, loops A to B and C to D, four XDs
#   xd-loop-two    SX40, loop A to B, the XDs on C and D removed
#   novastar-pair  MX40 Pro with a CVT10 and its backup box (backupOf)
#   straddle       VX1000 with a CVT4K-S backing up its own outputs
#   port-by-port   UHD Jr, two CVT10s backed up by one CVT4K-S
#   own-ports      UHD Jr, a CVT4K-S on the copy OPT backing its own ports
#   per-port       VX1000 per port, 1 backed up by 2 on the unit
#   halves         VX1000 per port, the back half backing the front
#   card-1to1      H9, card 1 backed up by card 2
#   mixed          H9 on Mixed: card 1 per port, card 2 backed up by card 3
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
    proj.snakes = [];
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
    const resolved = (id) => send('/api/processors', 'GET')
        .then(st => st.resolved.find(p => p.id === id));
    let proc, cardIx = 0, err = null;
    const check = (st) => { if (st && st.error && !err) err = st.error; return st; };
    if (shape === 'xd-loop' || shape === 'xd-loop-two') {
        proc = await add('brompton-sx40');
        check(await send(`/api/processors/${proc.id}`, 'PUT', { redundancy: true }));
        if (shape === 'xd-loop-two') {
            const r = await resolved(proc.id);
            for (const b of r.slots[0].card.cvts) {
                if (b.trunkIndex >= 2) {
                    check(await send(`/api/processors/${proc.id}/cvts/${b.id}`, 'DELETE'));
                }
            }
        }
    } else if (shape === 'novastar-pair') {
        proc = await add('novastar-mx40-pro');
        const c = proc.slots[0].card.id;
        check(await send(`/api/processors/${proc.id}/cards/${c}`, 'PUT', { mode: '20-port' }));
        check(await box(proc.id, c, { deviceId: 'novastar-cvt10' }));
    } else if (shape === 'straddle') {
        proc = await add('novastar-vx1000');
        check(await box(proc.id, proc.slots[0].card.id,
                        { deviceId: 'novastar-cvt4k-s', pair: false }));
    } else if (shape === 'port-by-port') {
        proc = await add('novastar-novapro-uhd-jr');
        const c = proc.slots[0].card.id;
        for (const d of ['novastar-cvt10', 'novastar-cvt10', 'novastar-cvt4k-s']) {
            check(await box(proc.id, c, { deviceId: d, pair: false }));
        }
    } else if (shape === 'own-ports') {
        proc = await add('novastar-novapro-uhd-jr');
        check(await box(proc.id, proc.slots[0].card.id,
                        { deviceId: 'novastar-cvt4k-s', trunk: 2 }));
    } else if (shape === 'per-port' || shape === 'halves') {
        proc = await add('novastar-vx1000');
        check(await send(`/api/processors/${proc.id}`, 'PUT',
                         { redundancy: true, cardsRedundancyMode: 'sequential' }));
        if (shape === 'halves') {
            const c = proc.slots[0].card.id;
            check(await send(`/api/processors/${proc.id}/cards/${c}`, 'PUT',
                             { redundancyMode: 'halves' }));
        }
    } else if (shape === 'card-1to1' || shape === 'mixed') {
        proc = await add('novastar-h9');
        const n = shape === 'mixed' ? 3 : 2;
        const cards = [];
        for (let i = 0; i < n; i++) {
            const st = check(await send(`/api/processors/${proc.id}/slots/${i}`, 'PUT',
                { deviceId: 'novastar-card-h-16xrj45-2xfiber' }));
            cards.push(st.processors.find(p => p.id === proc.id).slots[i].card.id);
        }
        check(await send(`/api/processors/${proc.id}`, 'PUT', { redundancy: true }));
        if (shape === 'card-1to1') {
            check(await send(`/api/processors/${proc.id}/cards/${cards[0]}`, 'PUT',
                             { backupCardId: cards[1] }));
        } else {
            check(await send(`/api/processors/${proc.id}`, 'PUT', { redundancyMixed: true }));
            check(await send(`/api/processors/${proc.id}/cards/${cards[0]}`, 'PUT',
                             { redundancyMode: 'sequential' }));
            check(await send(`/api/processors/${proc.id}/cards/${cards[1]}`, 'PUT',
                             { backupCardId: cards[2] }));
        }
    }
    if (err) return { error: err, shape };
    await app.refreshProcessors();
    const card = app._processorsResolved.find(p => p.id === proc.id)
        .slots[cardIx].card;
    const cvts = card.cvts || [];
    let boxId = null, ports;
    const near = cvts.find(b => cvts.some(c => c.backupOf === b.id))
        || cvts.find(b => app.boxStraddles(b))
        || cvts.find(b => (b.backedUpBy || []).length);
    if (near && shape !== 'own-ports') {
        boxId = near.id;
        ports = app.boxMainPorts(near);
    } else {
        ports = card.ports.filter(p => !p.cvtId);
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
    app.renderHardwareDock();
    app.resetHistory('Quick Fill Seed');
    return { proc: proc.id, card: card.id, wall: wall.id };
}"""

# What a fill must write: the socket of every port of BIG and the socket
# its backup comes back on, each under the key its store keeps it by -
# read through the assignment's pins and the tree's backedBy, never
# through the sheet.
EXPECTED_JS = """(wallId) => {
    const app = window.app;
    const wall = app.project.layers.find(l => l.id === wallId);
    const need = app.getLayerPortsRequired(wall);
    const out = [], unplaced = [];
    let backups = 0;
    for (let n = 1; n <= need; n++) {
        const pin = app._screenPortPin(wall, n);
        if (!pin) { unplaced.push(n); continue; }
        const own = app._dataPortOwner(pin.cardId, pin.port);
        out.push(`${own.id}:${pin.port}`);
        const bb = app._pullBackedBy(pin.cardId, pin.port);
        if (!bb) continue;
        const at = app._dataPortOwner(bb.cardId, bb.port, bb.cvtId || null);
        out.push(`${at.id}:${app.backupCableKey(bb) || String(bb.port)}`);
        backups += 1;
    }
    return { keys: out.sort(), unplaced, backups, need };
}"""

# Every length stored on any card or box of the show, and every socket
# any of them lists (the empty ones a fill must leave alone among them).
STORED_JS = """() => {
    const app = window.app;
    const out = {};
    let sockets = 0;
    (app._processorsResolved || []).forEach(p => (p.slots || []).forEach(s => {
        const card = s.card;
        if (!card) return;
        const recs = [['card', card]].concat((card.cvts || []).map(b => ['cvt', b]));
        recs.forEach(([kind, rec]) => {
            Object.entries(rec.portCables || {}).forEach(([k, v]) => {
                if (v && Number(v.ft) > 0) out[`${rec.id}:${k}`] = Number(v.ft);
            });
        });
        sockets += (card.ports || []).length;
    }));
    return { cables: out, sockets };
}"""

# Every card's and box's lengths forgotten, straight on the server.
CLEAR_CABLES_JS = """async () => {
    const app = window.app;
    const send = (url, body) => fetch(url, { method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body) }).then(r => r.json());
    for (const p of (app._processorsResolved || [])) {
        for (const s of (p.slots || [])) {
            if (!s.card) continue;
            await send(`/api/processors/${p.id}/cards/${s.card.id}`, { portCables: {} });
            for (const b of (s.card.cvts || [])) {
                await send(`/api/processors/${p.id}/cvts/${b.id}`, { portCables: {} });
            }
        }
    }
    await app.refreshProcessors();
    app.renderHardwareDock();
    app.resetHistory('Quick Fill Clear');
}"""

# The tray laid out for one state: every sheet down, the named sections
# folded, everything else open.
VIEW_JS = """([folds]) => {
    const app = window.app;
    try {
        for (let i = localStorage.length - 1; i >= 0; i--) {
            const k = localStorage.key(i);
            if (/^lrd_data_cable_sheet_|^ledRasterPanelCollapsed_hwdock-/.test(k)) {
                localStorage.removeItem(k);
            }
        }
        (app._processorsResolved || []).forEach(p => (p.slots || []).forEach(s => {
            if (!s.card) return;
            if (folds.includes('card')) {
                localStorage.setItem(`ledRasterPanelCollapsed_hwdock-card-${s.card.id}`, '1');
            }
            if (folds.includes('box')) {
                (s.card.cvts || []).forEach(b => localStorage.setItem(
                    `ledRasterPanelCollapsed_hwdock-box-${b.id}`, '1'));
            }
        }));
    } catch (_) { /* no storage */ }
    app.renderHardwareDock();
}"""

# The section folds as the tray shows them.
FOLDS_JS = """() => [...document.querySelectorAll('[data-lrd-sec-id^="hwdock-card-"], '
    + '[data-lrd-sec-id^="hwdock-box-"]')]
    .filter(s => s.getClientRects().length > 0)
    .map(s => [s.dataset.lrdSecId, s.classList.contains('lrd-sec-collapsed')])"""

# The ≡ buttons a user can see that are not flipped yet: a card's or a
# box's (`proc` false), or a processor's (`proc` true).
CLOSED_JS = """(proc) => [...document.querySelectorAll(
        proc ? '.hw-dock-cablebtn-proc' : '.hw-dock-cablebtn-data')]
    .filter(b => b.getClientRects().length > 0
            && !b.classList.contains('hw-dock-cablebtn-on'))
    .map(b => b.dataset.lrdField)"""

# The quick fill's all 100' buttons a user can see: on the cards' and the
# boxes' own sheets, or in the processors' lists.
FILLS_JS = """(proc) => [...document.querySelectorAll('[data-lrd-field]')]
    .filter(b => b.tagName === 'BUTTON' && b.getClientRects().length > 0
            && (proc ? /^proclist-.+-data-cable-fill-.+-100$/
                     : /^data-cable-fill-.+-100$/).test(b.dataset.lrdField)
            && !/-any-/.test(b.dataset.lrdField))
    .map(b => b.dataset.lrdField)"""

# Every cable row the visible sheets list, as `<card or box id>:<key>`.
LISTED_JS = """() => {
    const app = window.app;
    const ids = [];
    (app._processorsResolved || []).forEach(p => (p.slots || []).forEach(s => {
        if (!s.card) return;
        ids.push(s.card.id);
        (s.card.cvts || []).forEach(b => ids.push(b.id));
    }));
    ids.sort((a, b) => b.length - a.length);
    const out = new Set();
    document.querySelectorAll('input.hw-dock-cable-ft').forEach(f => {
        if (!f.getClientRects().length) return;
        const m = /(?:^|-)data-cable-ft-(.+)$/.exec(f.dataset.lrdField || '');
        if (!m) return;
        const id = ids.find(i => m[1].startsWith(`${i}-`));
        if (id) out.add(`${id}:${m[1].slice(id.length + 1)}`);
    });
    return [...out].sort();
}"""

INDEX_JS = """() => ({ index: window.app.historyIndex,
    action: window.app.history[window.app.historyIndex].action })"""

PULL_JS = """() => {
    const list = window.app.buildPullList();
    const scr = Object.values(list.byScreen || {}).find(s => s.name === 'BIG');
    return (scr ? scr.ports : []).map(p => ({
        num: p.num, cable: p.cable,
        backup: p.backup ? p.backup.cable : 'none' }));
}"""

SHAPES = ['xd-loop', 'xd-loop-two', 'novastar-pair', 'straddle',
          'port-by-port', 'own-ports', 'per-port', 'halves', 'card-1to1',
          'mixed']

# The tray states that offer a quick fill: the open tray (every card's and
# box's own ≡), the strips folded (a loop's one ≡), the cards folded (a
# card's one ≡ over its own backups), and the processor's own ≡ with the
# tray open or minimized.
STATES = {
    'open': ([], False),
    'strips-folded': (['box'], False),
    'cards-folded': (['card', 'box'], False),
    'processor-list-open': ([], True),
    'processor-list-minimized': (['card', 'box'], True),
}


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


def _lay_out(page, state):
    folds, proc = STATES[state]
    page.evaluate(VIEW_JS, [folds])
    landed(page)
    shown = dict(page.evaluate(FOLDS_JS))
    for sec, folded in shown.items():
        want = ('card' in folds) if sec.startswith('hwdock-card-') \
            else ('box' in folds)
        assert folded == want, (state, sec, shown)
    for _ in range(12):
        shut = page.evaluate(CLOSED_JS, proc)
        if not shut:
            break
        page.locator(f'[data-lrd-field="{shut[0]}"]').first.click()
        landed(page)
    assert not page.evaluate(CLOSED_JS, proc), state
    return page.evaluate(FILLS_JS, proc)


@pytest.mark.parametrize('state', list(STATES))
@pytest.mark.parametrize('shape', SHAPES)
def test_quick_fill_writes_every_port_in_use_and_its_backup(page, shape, state):
    pg, errors = page
    seed = pg.evaluate(SEED_JS, shape)
    assert 'error' not in seed, seed
    landed(pg)
    want = pg.evaluate(EXPECTED_JS, seed['wall'])
    assert not want['unplaced'], want
    assert want['backups'] == want['need'], (
        f'fixture: every port of BIG has a backup in {shape}: {want}')
    stored = pg.evaluate(STORED_JS)
    assert stored['cables'] == {}, stored
    assert stored['sockets'] > len(want['keys']), (
        f'fixture: {shape} must leave empty sockets to skip: {stored} {want}')

    fills = _lay_out(pg, state)
    if not fills:
        # A minimized SX40 shows no ≡ but the processor's: nothing here
        # to press, which is the case the processor's list is for.
        assert state == 'cards-folded', (shape, state)
        assert shape in ('xd-loop', 'xd-loop-two', 'novastar-pair',
                         'straddle', 'port-by-port'), (shape, state)
        return
    # What the sheets on show list must hold every port in use and its
    # backup, except with the cards folded: a box inside a folded card is
    # reached through the processor's list (owner, 2026-11-04).
    listed = pg.evaluate(LISTED_JS)
    reach = sorted(set(want['keys']) & set(listed))
    if state != 'cards-folded':
        assert reach == want['keys'], (
            f'{shape} / {state}: the sheets do not list '
            f'{sorted(set(want["keys"]) - set(listed))}')
    entries = 0
    for key in fills:
        before = pg.evaluate(INDEX_JS)['index']
        pg.locator(f'[data-lrd-field="{key}"]').first.click()
        landed(pg)
        after = pg.evaluate(INDEX_JS)
        assert after['index'] - before in (0, 1), (key, before, after)
        if after['index'] != before:
            assert after['action'] == 'Set Port Cable', after
            entries += 1

    got = settled(pg, lambda: pg.evaluate(STORED_JS),
                  lambda s: sorted(s['cables']) == reach)
    assert sorted(got['cables']) == reach, (
        f'{shape} / {state}: pressed {fills}\n'
        f'missing {sorted(set(reach) - set(got["cables"]))}\n'
        f'not wanted {sorted(set(got["cables"]) - set(reach))}')
    # (a folded card listing only empty ports writes nothing at all)
    assert set(got['cables'].values()) <= {100}, got

    # the pull sheet reads the length on every port and every backup
    if reach == want['keys']:
        pull = pg.evaluate(PULL_JS)
        assert len(pull) == want['need'], pull
        for p in pull:
            assert p['cable'] and p['cable'].startswith("100'"), pull
            assert p['backup'] and p['backup'].startswith("100'"), pull

    # each press that wrote was ONE undo step, however many boxes it wrote
    for _ in range(entries):
        pg.evaluate('() => window.app.undo()')
        landed(pg)
    back = settled(pg, lambda: pg.evaluate(STORED_JS),
                   lambda s: s['cables'] == {})
    assert back['cables'] == {}, back
    pg.evaluate(CLEAR_CABLES_JS)
    landed(pg)
    assert not errors, errors


@pytest.mark.parametrize('shape', ['xd-loop-two', 'card-1to1'])
def test_none_still_clears_every_port_even_an_empty_one(page, shape):
    """none forgets every row the sheet lists, a stale length on an empty
    socket included: it is the way to clean one up."""
    pg, errors = page
    seed = pg.evaluate(SEED_JS, shape)
    assert 'error' not in seed, seed
    landed(pg)
    # a length typed on every socket, empty ones included, as an older
    # fill wrote them
    pg.evaluate("""async () => {
        const app = window.app;
        const send = (url, body) => fetch(url, { method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body) }).then(r => r.json());
        for (const p of app._processorsResolved) for (const s of p.slots) {
            if (!s.card) continue;
            const recs = [[`/api/processors/${p.id}/cards/${s.card.id}`,
                           s.card.ports.filter(x => !x.cvtId)]]
                .concat((s.card.cvts || []).map(b => [
                    `/api/processors/${p.id}/cvts/${b.id}`, b.ports]));
            for (const [url, ports] of recs) {
                const cables = {};
                ports.forEach(x => { cables[String(x.number)] = { ft: 25 }; });
                if (ports.length) await send(url, { portCables: cables });
            }
        }
        await app.refreshProcessors();
        app.renderHardwareDock();
        app.resetHistory('Stale Lengths');
    }""")
    landed(pg)
    assert pg.evaluate(STORED_JS)['cables'], 'fixture: stale lengths stored'
    _lay_out(pg, 'processor-list-minimized')
    nones = pg.evaluate("""() => [...document.querySelectorAll('button[data-lrd-field]')]
        .filter(b => b.getClientRects().length > 0
                && /^proclist-.+-data-cable-fill-.+-none$/.test(b.dataset.lrdField))
        .map(b => b.dataset.lrdField)""")
    assert nones, 'the processor list offers none'
    for key in nones:
        pg.locator(f'[data-lrd-field="{key}"]').first.click()
        landed(pg)
    got = settled(pg, lambda: pg.evaluate(STORED_JS),
                  lambda s: s['cables'] == {})
    assert got['cables'] == {}, got
    pg.evaluate(CLEAR_CABLES_JS)
    landed(pg)
    assert not errors, errors


def test_a_ticked_backup_row_on_a_folded_loop_takes_the_typed_length(page):
    """With ticked: Fill on a folded XD loop writes the ticked row of the
    far box too (it is the sheet's row), as ONE undo step."""
    pg, errors = page
    seed = pg.evaluate(SEED_JS, 'xd-loop-two')
    assert 'error' not in seed, seed
    landed(pg)
    want = pg.evaluate(EXPECTED_JS, seed['wall'])
    _lay_out(pg, 'strips-folded')
    # tick the first port of BIG and its backup on the far XD
    picked = pg.evaluate("""(wallId) => {
        const app = window.app;
        const wall = app.project.layers.find(l => l.id === wallId);
        const pin = app._screenPortPin(wall, 1);
        const bb = app._pullBackedBy(pin.cardId, pin.port);
        const a = app._dataPortOwner(pin.cardId, pin.port);
        const b = app._dataPortOwner(bb.cardId, bb.port, bb.cvtId || null);
        return [[a.id, pin.port], [b.id, bb.port]];
    }""", seed['wall'])
    near = picked[0][0]
    for owner_id, socket in picked:
        pg.locator(f'[data-lrd-field="data-snake-tick-{owner_id}-{socket}"]').first.check()
    before = pg.evaluate(INDEX_JS)['index']
    pg.locator(f'[data-lrd-field="data-cable-ticked-fill-{near}"]').first.fill('42')
    pg.locator(f'[data-lrd-field="data-cable-ticked-fill-{near}-btn"]').first.click()
    landed(pg)
    got = settled(pg, lambda: pg.evaluate(STORED_JS),
                  lambda s: len(s['cables']) == 2)
    assert got['cables'] == {f'{picked[0][0]}:{picked[0][1]}': 42,
                             f'{picked[1][0]}:{picked[1][1]}': 42}, (got, want)
    after = pg.evaluate(INDEX_JS)
    assert after['index'] == before + 1 and after['action'] == 'Set Port Cable', after
    pg.evaluate('() => window.app.undo()')
    landed(pg)
    assert settled(pg, lambda: pg.evaluate(STORED_JS),
                   lambda s: s['cables'] == {})['cables'] == {}
    pg.evaluate(CLEAR_CABLES_JS)
    landed(pg)
    assert not errors, errors


# ── power: a circuit with no panels takes no cable ───────────────────────
#
# WALL: 4 wide x 4 rows of 200 W cabinets at 208 V, drawn by hand as four
# circuits, one a row, on multi 1 of distro SR. Row 3's cabinets are then
# blanked and row 4's removed, each with the app's own cabinet toggles:
# circuits 3 and 4 stay drawn and stay on the box with nothing to feed.
POWER_SEED_JS = """async () => {
    const app = window.app;
    const send = (url, method, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) })
        .then(r => r.json());
    try {
        for (let i = localStorage.length - 1; i >= 0; i--) {
            const k = localStorage.key(i);
            if (/^lrd_cable_sheet_|^ledRasterPanelCollapsed_hwdock-/.test(k)) {
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
    await send('/api/layer/add', 'POST', { name: 'WALL', columns: 4, rows: 4,
        cabinet_width: 200, cabinet_height: 200 });
    const p1 = await (await fetch('/api/project')).json();
    const id = p1.layers[0].id;
    const paths = {};
    for (let r = 0; r < 4; r++) {
        paths[r + 1] = [0, 1, 2, 3].map(c => ({ row: r, col: c }));
    }
    await send(`/api/layer/${id}`, 'PUT', {
        powerVoltage: 208, powerAmperage: 12.5, panelWatts: 200,
        processorType: 'novastar-coex-1g',
        powerFlowPattern: 'custom', powerCustomPaths: paths,
        powerCustomIndex: 5 });
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('quick_fill_power_setup');
    const wall = app.project.layers.find(l => l.id === id);
    app.selectLayer(wall);
    const d = app.addDistro({ name: 'SR' });
    app.setSocaDistro(wall, 1, d.id);
    app.setSocaNumber(wall, 1, 1);
    app.renderLayers();
    app._circuitTailCache = null;
    app.renderHardwareDock();
    return { id, distroId: d.id };
}"""

TOGGLE_JS = """async ([id, row, kind]) => {
    const app = window.app;
    const wall = app.project.layers.find(l => l.id === id);
    for (const p of wall.panels.filter(x => x.row === row)) {
        if (kind === 'blank') app.togglePanelBlank(id, p.id);
        else app.togglePanelHidden(id, p.id);
        await new Promise(r => setTimeout(r, 60));
    }
}"""

LEGS_JS = """(id) => {
    const app = window.app;
    const wall = app.project.layers.find(l => l.id === id);
    app._circuitTailCache = null;
    const s = app.getSocaPlan(wall).find(x => x.soca === 1);
    return s ? s.legs.map(g => [g.circuit, g.tiles]) : [];
}"""

POWER_STATE_JS = """(id) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === id);
    return {
        cables: JSON.parse(JSON.stringify(l.powerCircuitCables || {})),
        action: app.history[app.historyIndex].action,
        index: app.historyIndex,
    };
}"""


@pytest.fixture(scope="module")
def power_page(e2e_server, pw_browser):
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
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'power'")
    landed(pg)
    yield pg, errors
    context.close()


@pytest.mark.parametrize('folded', [False, True])
def test_power_quick_fill_skips_circuits_with_no_panels(power_page, folded):
    pg, errors = power_page
    ids = pg.evaluate(POWER_SEED_JS)
    landed(pg)
    pg.evaluate(TOGGLE_JS, [ids['id'], 2, 'blank'])
    landed(pg)
    pg.evaluate(TOGGLE_JS, [ids['id'], 3, 'hidden'])
    landed(pg)
    legs = settled(pg, lambda: pg.evaluate(LEGS_JS, ids['id']),
                   lambda v: v == [[1, 4], [2, 4], [3, 0], [4, 0]])
    assert legs == [[1, 4], [2, 4], [3, 0], [4, 0]], (
        f'fixture: circuits 3 and 4 stay on the box with no panels: {legs}')
    pg.evaluate("() => window.app.resetHistory('Power Quick Fill Seed')")
    d = ids['distroId']
    if folded:
        # the multi folded: its sheet still rides above the fold
        pg.evaluate(f"""() => {{ try {{ localStorage.setItem(
            'ledRasterPanelCollapsed_hwdock-multi-{d}-1', '1'); }} catch (_) {{}}
            window.app.renderHardwareDock(); }}""")
        landed(pg)
    pg.locator(f'[data-lrd-field="power-cable-sheet-{d}-1"]').click()
    landed(pg)
    # every circuit on the box has its row, the empty ones included
    rows = pg.evaluate(f"""() => [...document.querySelectorAll(
        '[data-lrd-field^="power-cable-ft-{ids["id"]}-"]')]
        .map(f => f.dataset.lrdField)""")
    assert rows == [f'power-cable-ft-{ids["id"]}-{n}' for n in (1, 2, 3, 4)], rows
    index = pg.evaluate(POWER_STATE_JS, ids['id'])['index']
    pg.locator(f'[data-lrd-field="power-cable-fill-{d}-1-10"]').click()
    landed(pg)
    st = settled(pg, lambda: pg.evaluate(POWER_STATE_JS, ids['id']),
                 lambda s: s['cables'] != {})
    assert st['cables'] == {'1': {'ft': 10, 'connector': None},
                            '2': {'ft': 10, 'connector': None}}, (
        f'only the circuits feeding panels take a cable: {st}')
    assert st['action'] == 'Set Circuit Cable' and st['index'] == index + 1, st
    # the typed length the same
    box = pg.locator(f'[data-lrd-field="power-cable-fill-any-{d}-1"]')
    box.fill('15')
    box.press('Enter')
    landed(pg)
    st = settled(pg, lambda: pg.evaluate(POWER_STATE_JS, ids['id']),
                 lambda s: s['cables'].get('1', {}).get('ft') == 15)
    assert st['cables'] == {'1': {'ft': 15, 'connector': None},
                            '2': {'ft': 15, 'connector': None}}, st
    assert st['index'] == index + 2, st
    # the pull sheet counts two circuit cables, none on the empty circuits
    pull = pg.evaluate("""(id) => {
        const list = window.app.buildPullList();
        const scr = Object.values(list.byScreen || {}).find(s => s.name === 'WALL');
        const box = scr && scr.boxes.find(b => b.circuits && b.circuits.length);
        return box ? box.circuits.map(c => [c.num, c.cable]) : null;
    }""", ids['id'])
    assert pull == [[1, "15' TRUE1"], [2, "15' TRUE1"], [3, None], [4, None]], pull
    # none clears every circuit, an empty one's stale cable included
    pg.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app.setCircuitCable(l, 3, { ft: 8, connector: null });
        app.renderHardwareDock();
    }""", ids['id'])
    landed(pg)
    pg.locator(f'[data-lrd-field="power-cable-fill-{d}-1-none"]').click()
    landed(pg)
    st = settled(pg, lambda: pg.evaluate(POWER_STATE_JS, ids['id']),
                 lambda s: s['cables'] == {})
    assert st['cables'] == {}, st
    assert not errors, errors
