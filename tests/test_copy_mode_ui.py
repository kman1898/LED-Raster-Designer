"""Mirror screens, copy boxes and the per-port card-or-box choice in the
browser (owner's rulings, 2026-10-30 and 2026-11-01).

"The copy screen's port map follows the first automatically and can't be
drawn separately." Since 2026-11-01 a mirror is made by DRAGGING, not by a
Screen Info pick: "Mirroring is driven by the card's existing Copy setting
plus dragging." A card in Copy mode dropped on a first screen feeds it; the
same card dropped on a second, matching screen makes it the first one's copy
(app-mirror-screens.js _copyDropPlan). A mismatch is refused with the reason;
the mirror's data controls refuse out loud; its runs land on the copy box
(H_4xfiber Copy mode: "OPT 3 copies the output on OPT 1", H15 Video Wall
Splicer Specifications V1.15.0 p.36) and print on the pull sheet and in the
tray like any run. Unplugging the source unplugs the copy; unplugging the
copy alone just removes the copy. A card in Independent mode drops as it
always did.

An MX40 Pro box going on OPT 3 in 20-port mode asks Mirror or Backup (User
Manual V1.5.0 p.9: "OPT 3 is the copy channel of OPT 1"; owner: "Either, you
pick"), and each of its ports 1-20 plugs in at the unit's RJ45 or at the box
("You can use the optical port alongside the physical Ethernet port").

Run locally:
    python -m pytest tests/test_copy_mode_ui.py -v --browser chromium
"""
import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const add = (name, columns, x, y) => j('POST', '/api/layer/add', {name,
        columns, rows: 3, cabinet_width: 256, cabinet_height: 256,
        offset_x: x, offset_y: y || 0});
    await add('SL', 4, 0); await add('SR', 4, 1100); await add('WIDE', 5, 2200);
    await add('IA', 2, 0, 900); await add('IB', 2, 600, 900);
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`,
                 {deviceId: 'novastar-card-h-4xfiber'});
    const cid = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cid}`, {mode: 'copy'});
    for (let i = 0; i < 4; i++) {
        await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`,
                {deviceId: 'novastar-cvt10', pair: false});
    }
    // a second H_4xfiber left in Independent: its second drag never mirrors
    st = await j('PUT', `/api/processors/${pid}/slots/1`,
                 {deviceId: 'novastar-card-h-4xfiber'});
    const ind = st.processors[0].slots[1].card.id;
    for (let i = 0; i < 2; i++) {
        await j('POST', `/api/processors/${pid}/cards/${ind}/cvts`,
                {deviceId: 'novastar-cvt10', pair: false});
    }
    const app = window.app;
    app.project = await (await fetch('/api/project')).json();
    await app.refreshProcessors();
    app.renderLayers();
    const byName = (n) => app.project.layers.find(l => l.name === n);
    await app.refreshPortAssignment();
    app.resetHistory('Mirror Seed');
    return {pid, cid, ind, sl: byName('SL').id, sr: byName('SR').id,
            wide: byName('WIDE').id, ia: byName('IA').id, ib: byName('IB').id};
}"""

# The tray's whole-card drop on a screen, through the same two calls the
# drag makes: the preview (_dockDataScreenTarget, what lights and what the
# pill says) and the release (_dockPerformDrop) - preview == result.
DROP_JS = """async ([cardId, layerId, type]) => {
    const app = window.app;
    const payload = type === 'processor'
        ? {type: 'processor', processorId: cardId}
        : {type: 'card', cardId, title: 'the card'};
    const target = app._dockDataScreenTarget({payload}, layerId, null);
    const status = document.getElementById('status-message');
    if (status) status.textContent = '';
    await app._dockPerformDrop(payload, target);
    await new Promise(r => setTimeout(r, 300));
    await app.refreshPortAssignment();
    const layer = app.project.layers.find(l => l.id === layerId);
    const scr = app._assignment.screens
        .find(s => s.layerId === String(layerId));
    return {pill: target.pill || null, lit: (target.nums || []).length,
            said: status ? status.textContent : '',
            mirrorOf: layer.dataMirrorOf === undefined ? null
                : layer.dataMirrorOf,
            required: scr ? scr.required : 0,
            ports: scr ? scr.ports.map(p => [p.cardId, p.port, p.source])
                : null};
}"""

SELECT_JS = """async (id) => {
    const app = window.app;
    const layer = app.project.layers.find(l => l.id === id);
    app.selectLayer(layer);
    app.updatePortCapacityDisplay();
    await new Promise(r => setTimeout(r, 50));
    return true;
}"""

TOASTS_JS = """() => {
    if (!window.__toasts) {
        window.__toasts = [];
        const orig = window.app._toast.bind(window.app);
        window.app._toast = (msg, err, ms) => {
            window.__toasts.push({msg: String(msg), err: !!err});
            return orig(msg, err, ms);
        };
    }
    const out = window.__toasts.slice();
    window.__toasts.length = 0;
    return out;
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(600)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    pg.evaluate(TOASTS_JS)
    yield pg, ids, errors
    context.close()


def drop(pg, card_id, layer_id, kind='card'):
    return pg.evaluate(DROP_JS, [card_id, layer_id, kind])


def test_screen_info_has_no_mirror_pick(page):
    pg, ids, errors = page
    pg.evaluate(SELECT_JS, ids['sr'])
    assert pg.locator('#mirror-screen-row').count() == 0
    assert pg.locator('#mirror-screen').count() == 0
    assert pg.locator('#mirror-screen-note').count() == 0
    assert errors == []


def test_the_first_drop_feeds_the_first_screen(page):
    pg, ids, errors = page
    out = drop(pg, ids['cid'], ids['sl'])
    assert out['mirrorOf'] is None
    assert out['pill']['ok'] and 'Copy of' not in out['pill']['text']
    assert [p[1] for p in out['ports']] == list(range(1, out['required'] + 1))
    assert {p[2] for p in out['ports']} == {'pin'}
    assert errors == []


def test_a_mismatched_second_screen_is_refused_with_the_reason(page):
    pg, ids, errors = page
    pg.evaluate(TOASTS_JS)
    out = drop(pg, ids['cid'], ids['wide'])
    assert out['pill'] == {'ok': True, 'text': 'Copy of SL'}
    toasts = pg.evaluate(TOASTS_JS)
    assert any(t['err'] and t['msg'] == (
        'WIDE is 5 x 3 cabinets and SL is 4 x 3 - a mirror screen must '
        'match the screen it copies.') for t in toasts), toasts
    assert out['mirrorOf'] is None
    # refused means nothing changed: WIDE took no ports of its own either
    assert all(p[0] is None for p in out['ports']), out['ports']
    assert errors == []


def test_the_second_drop_makes_the_copy_on_the_copy_outputs(page):
    pg, ids, errors = page
    out = drop(pg, ids['cid'], ids['sr'])
    # the preview says whose copy it is and lights the whole screen
    assert out['pill'] == {'ok': True, 'text': 'Copy of SL'}
    assert out['lit'] == out['required']
    assert out['mirrorOf'] == ids['sl']
    # H_4xfiber Copy: OPT 3 (sockets 17-24) copies OPT 1 (1-8)
    assert out['ports'][:2] == [[ids['cid'], 17, 'mirror'],
                                [ids['cid'], 18, 'mirror']], out
    assert all(p[2] == 'mirror' for p in out['ports'])
    more = pg.evaluate("""(ids) => {
        const app = window.app;
        const sr = app.project.layers.find(l => l.id === ids.sr);
        const sl = app.project.layers.find(l => l.id === ids.sl);
        const pins = app.project.port_assignments.pins
            .filter(p => p.layerId === String(ids.sr));
        return {flow: [sr.flowPattern, sl.flowPattern], pins: pins.length,
                occ: app._portOccupants(ids.cid, 17).map(o => o.name)};
    }""", ids)
    assert more['flow'][0] == more['flow'][1]
    assert more['pins'] == 0, 'the copy draws no path of its own'
    assert more['occ'] == ['SR']
    # dropping it there again changes nothing and says so
    again = drop(pg, ids['cid'], ids['sr'])
    assert again['said'] == 'SR already mirrors SL.'
    assert again['mirrorOf'] == ids['sl']
    assert errors == []


def test_the_mirrors_data_map_is_read_only_and_says_why(page):
    pg, ids, errors = page
    pg.evaluate(SELECT_JS, ids['sr'])
    pg.evaluate(TOASTS_JS)
    before = pg.evaluate("""(id) => window.app.project.layers
        .find(l => l.id === id).flowPattern""", ids['sr'])
    btn = pg.locator('.flow-pattern-btn[data-pattern="tr-v"]').first
    btn.scroll_into_view_if_needed()
    btn.click(force=True)
    pg.wait_for_timeout(200)
    toasts = pg.evaluate(TOASTS_JS)
    assert any(t['err'] and t['msg'] == (
        "SR mirrors SL - its data port map follows SL's and cannot be "
        "changed on its own. Change it on SL, or unplug the card from SR "
        "to stop mirroring.") for t in toasts), toasts
    after = pg.evaluate("""(id) => window.app.project.layers
        .find(l => l.id === id).flowPattern""", ids['sr'])
    assert after == before
    assert btn.evaluate("el => el.style.opacity") == '0.45'
    # the tray: a placement of the mirror's own ports is refused out loud
    pg.evaluate("""(ids) => window.app._assignmentRequest(
        '/api/port-assignments/place', 'POST',
        {layerId: String(ids.sr), index: 0, cardId: ids.cid, port: 5},
        null, 'Place Port')""", ids)
    toasts = pg.evaluate(TOASTS_JS)
    assert any(t['err'] and 'SR mirrors SL' in t['msg']
               and 'unplug the card from SR' in t['msg'] for t in toasts)
    assert errors == []


def test_the_mirror_follows_the_sources_map(page):
    pg, ids, errors = page
    out = pg.evaluate("""async (ids) => {
        const app = window.app;
        const sl = app.project.layers.find(l => l.id === ids.sl);
        const sr = app.project.layers.find(l => l.id === ids.sr);
        sl.flowPattern = 'bl-v';
        app.saveState('Change Flow');
        return [sl.flowPattern, sr.flowPattern];
    }""", ids)
    assert out == ['bl-v', 'bl-v']
    assert errors == []


def test_the_pull_sheet_and_the_box_show_the_mirrors_runs(page):
    pg, ids, errors = page
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const pull = app.buildPullList();
        const sr = pull.byScreen[ids.sr];
        const sl = pull.byScreen[ids.sl];
        const card = app._dockFindCard(ids.cid).card;
        const mirrorBox = card.cvts[2];
        // the binder's Ports table, wiring and processor sheets read a
        // socket's home through _bPortHome: the mirror socket is the
        // copy box's
        const home = app._bPortHome(ids.cid, 17);
        if (!home || !home.box || home.box.id !== mirrorBox.id) return null;
        return {sr: sr ? sr.ports.slice(0, 2).map(p => p.box) : null,
                sl: sl ? sl.ports.slice(0, 2).map(p => p.box) : null,
                title: app.pullBoxTitle(mirrorBox),
                taken: app.socketsTaken(ids.cid, mirrorBox.id)};
    }""", ids)
    assert out['sr'] == [out['title'], out['title']], out
    assert out['sl'][0] != out['title']
    assert out['taken']['taken'] == 2, out
    assert errors == []


MX40_JS = """async (mode) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const st = await j('POST', '/api/processors', {deviceId: 'novastar-mx40-pro'});
    const proc = st.processors[st.processors.length - 1];
    const cid = proc.slots[0].card.id;
    await j('PUT', `/api/processors/${proc.id}/cards/${cid}`, {mode});
    await window.app.refreshProcessors();
    window.app.renderHardwareDock();
    return {pid: proc.id, cid};
}"""


def test_an_mx40_pro_box_on_opt3_asks_mirror_or_backup(page):
    pg, ids, errors = page
    mx = pg.evaluate(MX40_JS, '20-port')
    pg.evaluate("(mx) => window.app._dockAddBox(mx.cid, 'novastar-cvt10')", mx)
    pg.wait_for_timeout(300)
    modal = pg.locator('#copy-role-modal')
    assert modal.is_visible()
    assert 'OPT 3 copies OPT 1' in pg.locator('#copy-role-text').inner_text()
    pg.locator('#copy-role-mirror').click()
    pg.wait_for_timeout(600)
    boxes = pg.evaluate("""(mx) => window.app._dockFindCard(mx.cid).card.cvts
        .map(b => [b.trunkTitle, b.copyRole, b.firstPort])""", mx)
    assert boxes == [['OPT 1', None, 1], ['OPT 3', 'mirror', 21]], boxes
    # the box gear flips it to Backup
    pg.evaluate("""(mx) => {
        const app = window.app;
        const found = app._dockFindCard(mx.cid);
        const cvt = found.card.cvts[1];
        const el = app._buildBoxCopyRoleStrip(found.proc, cvt);
        el.querySelector('[data-level="backup"]').click();
    }""", mx)
    pg.wait_for_timeout(600)
    box = pg.evaluate("""(mx) => window.app._dockFindCard(mx.cid).card.cvts[1]
        .firstPort""", mx)
    assert box == 1
    # Cancel adds nothing
    pg.evaluate("(mx) => window.app._dockAddBox(mx.cid, 'novastar-cvt10')", mx)
    pg.wait_for_timeout(300)
    pg.locator('#copy-role-cancel').click()
    pg.wait_for_timeout(400)
    assert pg.evaluate("(mx) => window.app._dockFindCard(mx.cid).card.cvts"
                       ".length", mx) == 2
    assert errors == []


def test_an_mx40_pro_port_plugs_in_at_the_unit_or_the_box(page):
    pg, ids, errors = page
    mx = pg.evaluate(MX40_JS, '40-port')
    pg.evaluate("""async (mx) => {
        await fetch(`/api/processors/${mx.pid}/cards/${mx.cid}/cvts`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({deviceId: 'novastar-cvt10'})});
        await window.app.refreshProcessors();
    }""", mx)
    out = pg.evaluate("""async (mx) => {
        const app = window.app;
        let found = app._dockFindCard(mx.cid);
        const port = found.card.ports.find(p => p.number === 3);
        const strip = app._buildPortPlugStrip(found.proc, found.card, port);
        const segs = [...strip.querySelectorAll('[data-level]')]
            .map(s => [s.dataset.level, s.textContent,
                       s.classList.contains('hw-pop-seg-on')]);
        strip.querySelector('[data-level="card"]').click();
        for (let i = 0; i < 40; i++) {
            await new Promise(r => setTimeout(r, 50));
            found = app._dockFindCard(mx.cid);
            if (found.card.ports.find(p => p.number === 3).plug === 'card') break;
        }
        const home = app._bPortHome(mx.cid, 3);
        const rows = app._buildCardPlugRows(found.proc, found.card);
        return {segs, plug: found.card.ports.find(p => p.number === 3).plug,
                box: home.box ? home.box.id : null,
                owner: app._dataPortOwner(mx.cid, 3).kind,
                rows: rows ? rows.textContent : ''};
    }""", mx)
    assert out['segs'] == [['card', 'Processor RJ45', False],
                           ['box', 'Breakout box', True]], out
    assert out['plug'] == 'card' and out['box'] is None
    assert out['owner'] == 'card'
    assert 'OPT 1: ports 1-10 (1 at the RJ45)' in out['rows'], out
    assert errors == []


STATE_JS = """(ids) => {
    const app = window.app;
    const sr = app.project.layers.find(l => l.id === ids.sr);
    const scr = (s) => app._assignment.screens
        .find(x => x.layerId === String(s));
    return {mirrorOf: sr.dataMirrorOf === undefined ? null : sr.dataMirrorOf,
            sr: scr(ids.sr).ports.map(p => [p.port, p.source]),
            sl: scr(ids.sl).ports.map(p => p.port)};
}"""


def test_unplugging_only_the_copy_just_removes_the_copy(page):
    pg, ids, errors = page
    # the copy's own run, cleared from its menu: a release of SR's port
    pg.evaluate("""(ids) => window.app._assignmentRequest(
        '/api/port-assignments/unpin', 'POST',
        {layerId: String(ids.sr), index: 0}, null, 'Release Port')""", ids)
    pg.wait_for_timeout(200)
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None
    assert all(p == [None, None] for p in st['sr']), st
    assert None not in st['sl'], 'the source keeps every port'
    # undo puts the copy back, as one step
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(600)
    pg.evaluate("() => window.app.refreshPortAssignment()")
    pg.wait_for_timeout(200)
    assert pg.evaluate(STATE_JS, ids)['mirrorOf'] == ids['sl']
    assert errors == []


def test_unplugging_the_source_unplugs_the_copy(page):
    pg, ids, errors = page
    if pg.evaluate(STATE_JS, ids)['mirrorOf'] is None:
        drop(pg, ids['cid'], ids['sr'])
    assert pg.evaluate(STATE_JS, ids)['mirrorOf'] == ids['sl']
    # Clear the card from the tray's menu: every screen port on it comes off
    pg.evaluate("""async (ids) => {
        const app = window.app;
        const pins = [];
        app._assignment.screens.forEach(s => s.ports.forEach(p => {
            if (p.cardId === ids.cid && s.layerId === String(ids.sl)) {
                pins.push({layerId: s.layerId, index: p.index});
            }
        }));
        await app._dockReleasePins(pins, 'Release Ports');
    }""", ids)
    pg.wait_for_timeout(300)
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None
    assert all(p is None for p in st['sl'])
    assert all(p == [None, None] for p in st['sr'])
    saved = pg.evaluate("""async (id) => (await (await fetch('/api/project'))
        .json()).layers.find(l => l.id === id).dataMirrorOf""", ids['sr'])
    assert saved is None
    assert errors == []


def test_an_independent_cards_second_drop_does_not_mirror(page):
    pg, ids, errors = page
    first = drop(pg, ids['ind'], ids['ia'])
    assert first['mirrorOf'] is None and first['ports'][0][2] == 'pin'
    out = drop(pg, ids['ind'], ids['ib'])
    assert 'Copy of' not in (out['pill'] or {}).get('text', '')
    assert out['mirrorOf'] is None
    assert out['ports'] and all(p[0] == ids['ind'] and p[2] == 'pin'
                                for p in out['ports']), out
    taken = {p[1] for p in first['ports']}
    assert not taken & {p[1] for p in out['ports']}
    assert errors == []


def test_an_mx40_pro_with_a_mirror_box_mirrors_by_dragging_the_processor(page):
    """The MX40 Pro is one unit (no cards to drag), so its processor line is
    the drag; its 20-port mode feeds a mirror where a box on OPT 3 is set to
    Mirror (User Manual V1.5.0 p.9, owner: "Either, you pick")."""
    pg, ids, errors = page
    mx = pg.evaluate(MX40_JS, '20-port')
    pg.evaluate("""async (mx) => {
        // the first box brings its OPT 3 pair, set to Mirror
        await fetch(`/api/processors/${mx.pid}/cards/${mx.cid}/cvts`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({deviceId: 'novastar-cvt10',
                                  copyRole: 'mirror'})});
        const add = (name, x) => fetch('/api/layer/add', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, columns: 2, rows: 2,
                cabinet_width: 256, cabinet_height: 256, offset_x: x,
                offset_y: 1800})}).then(r => r.json());
        const app = window.app;
        for (const [n, x] of [['MA', 0], ['MB', 700]]) {
            const layer = await add(n, x);
            app.initializeLayerDefaults(layer);
            layer.processorType = 'novastar-coex-1g';
            app.upsertProjectLayer(layer);
            app.updateLayers([layer]);
        }
        await app.refreshProcessors();
        app.renderLayers();
        await app.refreshPortAssignment();
    }""", mx)
    ma = pg.evaluate("() => window.app.project.layers.find(l => l.name === 'MA').id")
    mb = pg.evaluate("() => window.app.project.layers.find(l => l.name === 'MB').id")
    first = drop(pg, mx['pid'], ma, 'processor')
    assert first['mirrorOf'] is None and first['ports'][0][1] == 1
    out = drop(pg, mx['pid'], mb, 'processor')
    assert out['mirrorOf'] == ma
    assert out['ports'][0] == [mx['cid'], 21, 'mirror'], out
    assert errors == []
