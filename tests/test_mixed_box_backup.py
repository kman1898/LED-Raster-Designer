"""A backup box on a copy OPT backs up its primaries port by port.

The owner, 2026-11-02, on the shapes the one-to-one binding left alone (a
CVT4K-S on two copy OPTs behind two CVT10s, two CVT10s on copy OPTs behind
one CVT4K-S): "pair port by port". The backup box's sockets back up the same
port numbers on whichever primary boxes carry them, each socket numbered with
the port it backs up; a backup port never adds to the card's or processor's
port count; both boxes stay on the pull sheet. resolve_card derives the map
every resolve (`backsUpPorts` on the backup box, `backedUpBy` on each
primary) and stores nothing, so a saved show opens bound and undo follows.

Only products whose catalog mode carries a sourced `copyTrunks` take part:
the enhanced H_4xfiber in Backup, the MX40 Pro in 20-port and the NovaPro
UHD Jr (per box, Backup by default) are the shapes the owner's audit named.
"""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import processor_catalog as catalog  # noqa: E402

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


H4E = 'novastar-card-h-4xfiber-enhanced'
MX40 = 'novastar-mx40-pro'
UHD_JR = 'novastar-novapro-uhd-jr'
CVT10 = 'novastar-cvt10'
CVT4K = 'novastar-cvt4k-s'


def _ok(resp):
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()


def rig(client, unit, mode=None):
    device = catalog.get_device(unit)
    proc_id = 'novastar-h9' if device['kind'] == 'card' else unit
    st = _ok(client.post('/api/processors', json={'deviceId': proc_id}))
    pid = st['processors'][-1]['id']
    if device['kind'] == 'card':
        st = _ok(client.put(f'/api/processors/{pid}/slots/0',
                            json={'deviceId': unit}))
    cid = next(p for p in st['processors'] if p['id'] == pid
               )['slots'][0]['card']['id']
    if mode:
        set_mode(client, pid, cid, mode)
    return pid, cid


def set_mode(client, pid, cid, mode):
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': mode}))


def add_boxes(client, pid, cid, boxes):
    for device in boxes:
        _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                        json={'deviceId': device, 'pair': False}))


def card_of(client, cid):
    for proc in client.get('/api/processors').get_json()['resolved']:
        for slot in proc['slots']:
            if slot['card'] and slot['card']['id'] == cid:
                return slot['card']
    raise AssertionError(f'no card {cid}')


def mapping(card):
    """{backup box's OPTs: [(port, its socket, primary's OPTs, primary's
    own number)]} for every box backing anything up."""
    title = {b['id']: b['trunkTitle'] for b in card['cvts']}
    return {b['trunkTitle']: [(m['number'], m['socket'], title[m['boxId']],
                               m['local']) for m in b['backsUpPorts']]
            for b in card['cvts'] if b['backsUpPorts']}


def backed_by(card):
    title = {b['id']: b['trunkTitle'] for b in card['cvts']}
    return {b['trunkTitle']: [title[i] for i in b['backedUpBy']]
            for b in card['cvts'] if b['backedUpBy']}


def run(numbers, primary, local_first, socket_first=None):
    """Consecutive card ports on one primary box."""
    numbers = list(numbers)
    first = numbers[0]
    return [(n, n - first + (socket_first or first), primary,
             n - first + local_first) for n in numbers]


# (id, unit, backup mode, other mode, boxes in add order, map, count)
SHAPES = [
    # 1. a CVT4K-S on OPT 5-6 behind CVT10s on OPT 1 and 2
    ('h4e-cvt4k-behind-cvt10s', H4E, 'backup', 'copy',
     [CVT10] * 4 + [CVT4K],
     {'OPT 5-6': run(range(1, 11), 'OPT 1', 1)
      + run(range(11, 17), 'OPT 2', 1)}, 40),
    # 2. CVT10s on OPT 5 and 6 behind a CVT4K-S on OPT 1-2
    ('h4e-cvt10s-behind-cvt4k', H4E, 'backup', 'copy',
     [CVT4K, CVT4K, CVT10, CVT10],
     {'OPT 5': run(range(1, 11), 'OPT 1-2', 1),
      'OPT 6': run(range(11, 17), 'OPT 1-2', 11, socket_first=1)}, 32),
    # 3. a CVT4K-S on OPT 3-4 behind CVT10s on OPT 1 and 2 (8 each)
    ('uhdjr-cvt4k-behind-cvt10s', UHD_JR, None, None,
     [CVT10, CVT10, CVT4K],
     {'OPT 3-4': run(range(1, 9), 'OPT 1', 1)
      + run(range(9, 17), 'OPT 2', 1)}, 16),
    # 4. CVT10s on OPT 3 and 4 behind a CVT4K-S on OPT 1-2
    ('uhdjr-cvt10s-behind-cvt4k', UHD_JR, None, None,
     [CVT4K, CVT10, CVT10],
     {'OPT 3': run(range(1, 9), 'OPT 1-2', 1),
      'OPT 4': run(range(9, 17), 'OPT 1-2', 9, socket_first=1)}, 16),
    # 5. the MX40 Pro 20-port, the same two shapes
    ('mx40-cvt4k-behind-cvt10s', MX40, '20-port', '40-port',
     [CVT10, CVT10, CVT4K],
     {'OPT 3-4': run(range(1, 11), 'OPT 1', 1)
      + run(range(11, 17), 'OPT 2', 1)}, 20),
    ('mx40-cvt10s-behind-cvt4k', MX40, '20-port', '40-port',
     [CVT4K, CVT10, CVT10],
     {'OPT 3': run(range(1, 11), 'OPT 1-2', 1),
      'OPT 4': run(range(11, 17), 'OPT 1-2', 11, socket_first=1)}, 20),
]
IDS = [s[0] for s in SHAPES]
PARAMS = 'name,unit,mode,other,boxes,expected,count'


def _expected_backed_by(expected):
    out = {}
    for backup, rows in expected.items():
        for _n, _s, primary, _l in rows:
            if backup not in out.setdefault(primary, []):
                out[primary].append(backup)
    return out


def _check(card, expected, count):
    assert mapping(card) == expected
    assert backed_by(card) == _expected_backed_by(expected)
    # the one-to-one pair stays for boxes on the same OPTs only
    assert not any(b['backupOf'] for b in card['cvts'])
    # A backup port never adds to the count: the primaries' ports only.
    primaries = [p for p in card['ports'] if not p['mirrorOf']]
    assert card['ceiling'] == count, card['ceiling']
    assert card['defined'] == count, card['defined']
    assert len(primaries) == count
    backups = {b['id'] for b in card['cvts'] if b['copyRole'] == 'backup'}
    assert not any(p['cvtId'] in backups for p in card['ports'])
    # ...and a backup box lists exactly the ports it backs up
    for box in card['cvts']:
        if box['id'] in backups:
            assert [p['number'] for p in box['ports']] \
                == [m['number'] for m in box['backsUpPorts']]


@pytest.mark.parametrize(PARAMS, SHAPES, ids=IDS)
def test_the_backup_box_backs_up_port_by_port(client, name, unit, mode, other,
                                              boxes, expected, count):
    pid, cid = rig(client, unit, mode)
    add_boxes(client, pid, cid, boxes)
    _check(card_of(client, cid), expected, count)


def test_ports_only_a_backup_box_reaches_are_not_counted(client):
    """The audit's case 2: CVT10s on OPT 5 and 6 behind CVT4K-S boxes on
    OPT 1-2 and 3-4. Ports 17-20 came only out of the OPT 6 backup, and the
    card read 36. The primaries carry 32."""
    pid, cid = rig(client, H4E, 'backup')
    add_boxes(client, pid, cid, [CVT4K, CVT4K, CVT10, CVT10])
    card = card_of(client, cid)
    assert card['ceiling'] == 32, card['ceiling']
    assert card['defined'] == 32, card['defined']
    numbers = [p['number'] for p in card['ports']]
    assert not any(17 <= n <= 20 for n in numbers), numbers
    assert sum(1 for p in card['ports'] if not p['mirrorOf']) == 32


def test_the_mx40_pros_own_ports_past_the_primary_box_stay_its_own(client):
    """MX40 Pro, CVT4K-S on OPT 1-2: ports 17-20 are its own RJ45s, not the
    OPT 4 backup box's - the backup box backs up 11-16 only."""
    pid, cid = rig(client, MX40, '20-port')
    add_boxes(client, pid, cid, [CVT4K, CVT10, CVT10])
    card = card_of(client, cid)
    face = [p['number'] for p in card['ports'] if not p['cvtId']]
    assert face == [17, 18, 19, 20]


@pytest.mark.parametrize(PARAMS, SHAPES, ids=IDS)
def test_a_saved_show_opens_bound_and_undo_follows(client, name, unit, mode,
                                                   other, boxes, expected,
                                                   count):
    """Nothing is stored: a delete frees the backup's sockets for that
    primary, and the whole-project PUT (undo, or opening the file) brings
    the map back."""
    pid, cid = rig(client, unit, mode)
    add_boxes(client, pid, cid, boxes)
    before = client.get('/api/project').get_json()
    raw = next(s['card'] for p in before['processors'] for s in p['slots']
               if s.get('card') and s['card']['id'] == cid)
    assert not any('backsUpPorts' in b or 'backedUpBy' in b
                   for b in raw['cvts'])
    first = next(b for b in card_of(client, cid)['cvts']
                 if b['trunkIndex'] == 0)
    _ok(client.delete(f'/api/processors/{pid}/cvts/{first["id"]}'))
    card = card_of(client, cid)
    assert not any(m['boxId'] == first['id']
                   for b in card['cvts'] for m in b['backsUpPorts'])
    _ok(client.put('/api/project', json=copy.deepcopy(before)))
    _check(card_of(client, cid), expected, count)


@pytest.mark.parametrize(PARAMS, SHAPES, ids=IDS)
def test_switching_away_and_back(client, name, unit, mode, other, boxes,
                                 expected, count):
    """Out of Backup (the card's other mode, or each copy box set to Mirror
    where the box picks) nothing backs anything up; back, the map returns."""
    pid, cid = rig(client, unit, mode)
    add_boxes(client, pid, cid, boxes)
    copies = [b['id'] for b in card_of(client, cid)['cvts'] if b['copyRole']]
    if other:
        set_mode(client, pid, cid, other)
    else:
        for box_id in copies:
            _ok(client.put(f'/api/processors/{pid}/cvts/{box_id}',
                           json={'copyRole': 'mirror'}))
    card = card_of(client, cid)
    assert not any(b['backsUpPorts'] or b['backedUpBy'] for b in card['cvts'])
    if other:
        set_mode(client, pid, cid, mode)
    else:
        for box_id in copies:
            _ok(client.put(f'/api/processors/{pid}/cvts/{box_id}',
                           json={'copyRole': 'backup'}))
    _check(card_of(client, cid), expected, count)


def test_a_one_to_one_pair_is_mapped_too_and_keeps_backup_of(client):
    pid, cid = rig(client, H4E, 'backup')
    add_boxes(client, pid, cid, [CVT10, CVT10, CVT10, CVT10, CVT10])
    card = card_of(client, cid)
    far = next(b for b in card['cvts'] if b['trunkTitle'] == 'OPT 5')
    near = next(b for b in card['cvts'] if b['trunkTitle'] == 'OPT 1')
    assert far['backupOf'] == near['id']
    assert mapping(card) == {'OPT 5': run(range(1, 11), 'OPT 1', 1)}
    assert near['backedUpBy'] == [far['id']]


# ── the tray, its sheets, the binder's words and the pull sheet ───────────

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

SEED_JS = """async ([unit, kind, mode, boxes]) => {
    const send = (url, method, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) })
        .then(r => r.json());
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await send('/api/project', 'PUT', proj);
    await send('/api/layer/add', 'POST', { name: 'WALL', columns: 4,
        rows: 4, cabinet_width: 200, cabinet_height: 200 });
    const st = await send('/api/processors', 'POST',
        { deviceId: kind === 'card' ? 'novastar-h9' : unit });
    const proc = st.processors[st.processors.length - 1];
    let card = proc.slots[0].card && proc.slots[0].card.id;
    if (kind === 'card') {
        const put = await send(`/api/processors/${proc.id}/slots/0`, 'PUT',
                               { deviceId: unit });
        card = put.processors.find(p => p.id === proc.id).slots[0].card.id;
    }
    if (mode) {
        await send(`/api/processors/${proc.id}/cards/${card}`, 'PUT',
                   { mode });
    }
    for (const box of boxes) {
        await send(`/api/processors/${proc.id}/cards/${card}/cvts`, 'POST',
                   { deviceId: box, pair: false });
    }
    await window.app.refreshProcessors();
    return { proc: proc.id, card };
}"""

TRAY_JS = """(cardId) => {
    const app = window.app;
    const card = app._processorsResolved.flatMap(p => p.slots)
        .map(s => s.card).find(c => c && c.id === cardId);
    const title = (id) => card.cvts.find(b => b.id === id).trunkTitle;
    const backups = card.cvts.filter(b => (b.backsUpPorts || []).length);
    const mains = card.cvts.filter(b => (b.backedUpBy || []).length);
    const strips = {};
    let unit = null;
    for (const near of mains) {
        const sec = document.querySelector(
            `[data-lrd-sec-id="hwdock-box-${near.id}"]`);
        if (!sec) { strips[near.trunkTitle] = null; continue; }
        unit = unit || sec.closest('.hw-dock-unit, .hw-dock-card');
        strips[near.trunkTitle] = {
            loop: sec.classList.contains('hw-dock-loop'),
            fars: [...sec.querySelectorAll('[data-lrd-loop-far]')].map(r => [
                title(r.dataset.lrdLoopFar),
                [...r.querySelectorAll('.lrd-tile-face')].map(f => parseInt(
                    f.querySelector('.lrd-tile-line span').textContent, 10)),
            ]),
        };
    }
    // the backup box's own cable sheet, flipped open: a row per socket,
    // numbered with the port it backs up
    const sheets = {};
    for (const b of backups) {
        app._setDataCableSheetOpen({ kind: 'cvt', id: b.id }, true);
    }
    app.renderHardwareDock();
    for (const b of backups) {
        const sheet = document.querySelector(
            `[data-lrd-cable-sheet="cvt:${b.id}"]`);
        sheets[b.trunkTitle] = sheet ? [...sheet.querySelectorAll('tr')]
            .filter(tr => tr.children[0] && tr.children[0].tagName === 'TD'
                    && !tr.classList.contains('hw-dock-cable-snake'))
            .map(tr => parseInt(tr.children[1].textContent, 10)) : null;
        app._setDataCableSheetOpen({ kind: 'cvt', id: b.id }, false);
    }
    app.renderHardwareDock();
    return {
        strips,
        sheets,
        alone: backups.filter(b => document.querySelector(
            `[data-lrd-sec-id="hwdock-box-${b.id}"]`)).map(b => b.trunkTitle),
        copyTag: !!unit && unit.textContent.includes('(copy)'),
        // the binder's Breakout boxes line and the box's ⚙ read this
        words: Object.fromEntries(backups.map(b => [b.trunkTitle,
            app.boxLoopText(b, card.cvts, x => x.trunkTitle)])),
        // the box sheet's Fiber section reads the loop as one group
        groups: Object.fromEntries(backups.map(b => {
            const g = app.fiberLoopGroup(b);
            return [b.trunkTitle, g ? [g.nears.map(x => x.trunkTitle),
                                       g.fars.map(x => x.trunkTitle)] : null];
        })),
        boxes: card.cvts.length,
        pulled: app._pullAllBoxes().filter(e => e.card.id === cardId).length,
        ceiling: card.ceiling,
    };
}"""


def _spans(rows):
    """'1-10, 1-6 as 11-16' style words, per primary, for one backup."""
    groups = {}
    for number, _socket, primary, local in rows:
        groups.setdefault(primary, ([], []))
        groups[primary][0].append(local)
        groups[primary][1].append(number)

    def text(ns):
        return f'{min(ns)}-{max(ns)}'
    parts = []
    for primary, (locals_, numbers) in groups.items():
        mine, shown = text(locals_), text(numbers)
        parts.append(f'{primary} {mine}'
                     + (f' as {shown}' if shown != mine else ''))
    return 'loop of ' + ', '.join(parts)


@pytest.mark.parametrize(PARAMS, SHAPES, ids=IDS)
def test_the_tray_draws_each_backup_socket_in_its_primarys_loop(
        e2e_server, pw_browser, name, unit, mode, other, boxes, expected,
        count):
    kind = catalog.get_device(unit)['kind']
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 1100})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    page = context.new_page()
    try:
        page.goto(e2e_server, wait_until='domcontentloaded')
        page.wait_for_function(
            "() => window.app && window.app._initialLoadComplete === true"
            " && window.app._socketConnects >= 1")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        ids = page.evaluate(SEED_JS, [unit, kind, mode, boxes])
        page.locator('[data-mode="data-flow"]').click()
        page.wait_for_function(
            "() => window.canvasRenderer.viewMode === 'data-flow'")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        tray = page.evaluate(TRAY_JS, ids['card'])
    finally:
        context.close()
    # every primary's strip is a loop ending in a row per backup box, each
    # socket numbered with the card port it backs up
    want = {}
    for backup, rows in expected.items():
        for number, _socket, primary, _local in rows:
            fars = want.setdefault(primary, [])
            if not fars or fars[-1][0] != backup:
                fars.append([backup, []])
            fars[-1][1].append(number)
    assert set(tray['strips']) == set(want), tray['strips']
    for primary, fars in want.items():
        strip = tray['strips'][primary]
        assert strip and strip['loop'], (primary, strip)
        assert strip['fars'] == fars, (primary, strip['fars'])
    # no backup box drawn on its own, and no "(copy)" box of free sockets
    assert tray['alone'] == [], tray['alone']
    assert not tray['copyTag']
    # the backup's cable sheet: every socket, by the port it backs up
    assert tray['sheets'] == {b: [r[0] for r in rows]
                              for b, rows in expected.items()}
    assert tray['words'] == {b: _spans(rows) for b, rows in expected.items()}
    for backup, rows in expected.items():
        nears, fars = tray['groups'][backup]
        assert backup in fars
        assert {r[2] for r in rows} <= set(nears)
    # both boxes of every loop on the pull sheet; no backup port counted
    assert (tray['boxes'], tray['pulled'], tray['ceiling']) \
        == (len(boxes), len(boxes), count)
