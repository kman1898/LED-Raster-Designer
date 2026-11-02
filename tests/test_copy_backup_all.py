"""Every NovaStar unit whose own documents name a copy or backup OPT gets the
copy OPT handling (owner, 2026-11-02: "Any processor that supports hot
backup or copy will need to support this in our app").

The rule (resolve_card, copy_trunks) reads the catalog mode's copyTrunks
only, and each entry quotes its own source (test_copy_mode.py's
COPY_SOURCES checks the words):

  * VX400 Pro, VX600 Pro, VX1000 Pro: OPT 2, and the VX2000 Pro: OPT 3/4,
    each set to Copy or Backup for the whole unit (VX Pro Series User
    Manual, Table 5-7 OPT working mode) - two modes, Backup the default,
    like the H_4xfiber's. A file saved before reads Backup.
  * MCTRL660 Pro: "OPT2 is the backup input or output port of OPT1"
    (Specifications V1.4.1 p.4) - backup only.
  * MCTRL R5 ("copy channel" on its sheet, "backup" on its product page)
    and MCTRL4K ("duplicate channel" on its sheet, "backup input/output
    ports" on its product page) - each box on a copy OPT picks Mirror or
    Backup, Backup the default, like the NovaPro UHD.
  * MX30 and MX20: "OPT 2 is the copy channel of OPT 1" and nothing says
    backup - a box there feeds a mirror, with no choice.

A box on a copy OPT that backs up is the loop partner of the box on the OPT
it copies, whichever went on first, but only where the two take exactly
the same OPTs (a mixed shape is the owner's to rule on, and stays
unbound). No copy OPT adds a port: every count stays the unit's own.
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


VX400P = 'novastar-vx400-pro'
VX600P = 'novastar-vx600-pro'
VX1000P = 'novastar-vx1000-pro'
VX2000P = 'novastar-vx2000-pro'
M660P = 'novastar-mctrl660-pro'
R5 = 'novastar-mctrl-r5'
M4K = 'novastar-mctrl4k'
MX30 = 'novastar-mx30'
MX20 = 'novastar-mx20'
CVT10 = 'novastar-cvt10'
CVT4K = 'novastar-cvt4k-s'

VX_PROS = (VX400P, VX600P, VX1000P, VX2000P)
PER_BOX = (R5, M4K)
MIRROR_ONLY = (MX30, MX20)

ONE_COPY = [('OPT 1', None, None), ('OPT 2', 'backup', 'OPT 1')]
TWO_COPIES = [('OPT 1', None, None), ('OPT 2', None, None),
              ('OPT 3', 'backup', 'OPT 1'), ('OPT 4', 'backup', 'OPT 2')]
WIDE_COPY = [('OPT 1-2', None, None), ('OPT 3-4', 'backup', 'OPT 1-2')]


def _ok(resp):
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()


def rig(client, unit, mode=None):
    """A processor that is the all-in-one `unit`, set to `mode` if given.
    Returns (pid, cid)."""
    st = _ok(client.post('/api/processors', json={'deviceId': unit}))
    proc = st['processors'][-1]
    pid, cid = proc['id'], proc['slots'][0]['card']['id']
    if mode:
        set_mode(client, pid, cid, mode)
    return pid, cid


def set_mode(client, pid, cid, mode):
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': mode}))


def add_box(client, pid, cid, device, **body):
    return _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                           json=dict({'deviceId': device}, **body)))


def set_role(client, pid, box_id, role):
    return client.put(f'/api/processors/{pid}/cvts/{box_id}',
                      json={'copyRole': role})


def card_of(client, cid):
    for proc in client.get('/api/processors').get_json()['resolved']:
        for slot in proc['slots']:
            if slot['card'] and slot['card']['id'] == cid:
                return slot['card']
    raise AssertionError(f'no card {cid}')


def raw_card(client, cid):
    for proc in client.get('/api/processors').get_json()['processors']:
        for slot in proc['slots']:
            if slot['card'] and slot['card']['id'] == cid:
                return slot['card']
    raise AssertionError(f'no card {cid}')


def pairs(card):
    """(OPTs of a box, its copy role, OPTs of the box it backs up) for
    every box, in OPT order."""
    title = {b['id']: b['trunkTitle'] for b in card['cvts']}
    return sorted((b['trunkTitle'], b['copyRole'], title.get(b['backupOf']))
                  for b in card['cvts'])


def primaries(card):
    return [p['number'] for p in card['ports'] if not p['mirrorOf']]


def _counts_hold(card, ports):
    """The copies add no port: the card shows the unit's own count."""
    assert card['ceiling'] == ports, card['ceiling']
    assert card['defined'] == ports, card['defined']
    assert len(primaries(card)) == ports


def _fill(client, pid, cid, box, body, n):
    for _ in range(n * 2):
        add_box(client, pid, cid, box, pair=False, **body)


# (unit, backup mode, other mode, box, add body, boxes per side, bound shape,
#  ports the unit shows)
SHAPES = [
    (VX400P, 'backup', 'copy', CVT10, {}, 1, ONE_COPY, 4),
    (VX600P, 'backup', 'copy', CVT10, {}, 1, ONE_COPY, 6),
    (VX1000P, 'backup', 'copy', CVT10, {}, 1, ONE_COPY, 10),
    (VX2000P, 'backup', 'copy', CVT10, {}, 2, TWO_COPIES, 20),
    (VX2000P, 'backup', 'copy', CVT4K, {}, 1, WIDE_COPY, 20),
    (VX2000P, 'backup', 'copy', CVT4K, {'inputs': 1}, 2, TWO_COPIES, 20),
    (M660P, None, None, CVT10, {}, 1, ONE_COPY, 6),
    (R5, None, None, CVT10, {}, 1, ONE_COPY, 8),
    (M4K, None, None, CVT10, {}, 2, TWO_COPIES, 16),
    (M4K, None, None, CVT4K, {}, 1, WIDE_COPY, 16),
    (M4K, None, None, CVT4K, {'inputs': 1}, 2, TWO_COPIES, 16),
]
IDS = [f'{s[0].replace("novastar-", "")}-{s[3].replace("novastar-", "")}'
       f'{"-1opt" if s[4] else ""}' for s in SHAPES]
WITH_MODES = [s for s in SHAPES if s[2]]
WITH_MODES_IDS = [i for i, s in zip(IDS, SHAPES) if s[2]]


# ── the catalog ───────────────────────────────────────────────────────────

def test_each_unit_reads_its_own_copy_kind_and_keeps_its_count():
    for unit in VX_PROS:
        device = catalog.get_device(unit)
        assert device['ports']['defaultMode'] == 'backup', unit
        assert catalog.copy_trunks(device) == 'backup', unit
        assert catalog.copy_trunks(device, 'backup') == 'backup', unit
        assert catalog.copy_trunks(device, 'copy') == 'mirror', unit
        # a file saved before the modes ran its one "default" mode: Backup
        assert catalog.canonical_mode(device, 'default') == 'backup', unit
        counts = {m['count'] for m in device['ports']['modes']}
        assert counts == {catalog.port_capacity(unit, 'default')['count']}
    for unit, kind in ([(M660P, 'backup')]
                       + [(u, 'per-box') for u in PER_BOX]
                       + [(u, 'mirror') for u in MIRROR_ONLY]):
        device = catalog.get_device(unit)
        assert [m['id'] for m in device['ports']['modes']] == ['default']
        assert catalog.copy_trunks(device, 'default') == kind, unit
    for unit in VX_PROS + (M660P,) + PER_BOX + MIRROR_ONLY:
        device = catalog.get_device(unit)
        # every OPT still carries the unit's own copper: no box adds a port,
        # and no box brings a second one with it
        assert device['trunkDelivery'] == 'copy', unit
        assert not catalog.default_backup_pair(
            catalog.new_card(unit, 'sweep', fixed=True)), unit


def test_the_units_with_no_box_on_their_copy_opt_are_unchanged():
    """VX400 (no OPT rate stated), VX600 and VX1000 (OPT 2 not counted as a
    trunk) carry no copy trunks: nothing can go on the OPT that copies."""
    assert 'trunks' not in catalog.get_device('novastar-vx400')
    for unit in ('novastar-vx400', 'novastar-vx600', 'novastar-vx1000'):
        device = catalog.get_device(unit)
        assert (device.get('trunks') or 0) <= 1, unit
        assert not any(m.get('copyTrunks')
                       for m in device['ports']['modes']), unit


# ── the binding, whatever came first ──────────────────────────────────────

@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports', SHAPES,
                         ids=IDS)
def test_boxes_added_one_at_a_time_are_bound(client, unit, mode, other, box,
                                             body, n, bound, ports):
    """Nothing stored: the binding is read off the mode and the OPTs."""
    pid, cid = rig(client, unit, mode)
    _fill(client, pid, cid, box, body, n)
    card = card_of(client, cid)
    assert pairs(card) == bound
    _counts_hold(card, ports)
    assert not any(b.get('backupOf') for b in raw_card(client, cid)['cvts'])


@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports', SHAPES,
                         ids=IDS)
def test_a_normal_add_ends_bound(client, unit, mode, other, box, body, n,
                                 bound, ports):
    """The add as the tray sends it: a box comes alone on these units
    (their OPTs copy the unit's own copper), and the boxes added after it
    land on the copy OPTs as Backup."""
    pid, cid = rig(client, unit, mode)
    for _ in range(n * 2):
        add_box(client, pid, cid, box, **body)
    card = card_of(client, cid)
    assert pairs(card) == bound
    _counts_hold(card, ports)


@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports', SHAPES,
                         ids=IDS)
def test_the_box_on_the_copy_opt_going_on_first_is_bound(
        client, unit, mode, other, box, body, n, bound, ports):
    """The copy OPT's box first in the file, holding its OPT, and the
    primary's after it: the same pair."""
    pid, cid = rig(client, unit, mode)
    _fill(client, pid, cid, box, body, n)
    project = client.get('/api/project').get_json()
    card = card_of(client, cid)
    where = {b['id']: b['trunkIndex'] for b in card['cvts']}
    for proc in project['processors']:
        for slot in proc['slots']:
            raw = slot.get('card')
            if raw and raw['id'] == cid:
                for cvt in raw['cvts']:
                    cvt['trunk'] = where[cvt['id']]
                raw['cvts'].reverse()
    _ok(client.put('/api/project', json=project))
    card = card_of(client, cid)
    assert card['cvts'][0]['copyRole'] == 'backup'
    assert pairs(card) == bound
    _counts_hold(card, ports)


@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports',
                         WITH_MODES, ids=WITH_MODES_IDS)
def test_boxes_added_in_copy_mode_are_bound_once_backup_is_picked(
        client, unit, mode, other, box, body, n, bound, ports):
    pid, cid = rig(client, unit, other)
    _fill(client, pid, cid, box, body, n)
    card = card_of(client, cid)
    assert not any(b['backupOf'] for b in card['cvts'])
    # Copy: every copy box feeds a mirror of the box it copies
    copies = [b for b in card['cvts'] if b['copyRole']]
    assert copies and all(b['copyRole'] == 'mirror' and b['mirrorOf']
                          for b in copies)
    _counts_hold(card, ports)
    set_mode(client, pid, cid, mode)
    card = card_of(client, cid)
    assert pairs(card) == bound
    _counts_hold(card, ports)
    # and away again
    set_mode(client, pid, cid, other)
    assert not any(b['backupOf'] for b in card_of(client, cid)['cvts'])


@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports', SHAPES,
                         ids=IDS)
def test_deleting_a_primary_frees_its_partner_and_undo_binds_it_again(
        client, unit, mode, other, box, body, n, bound, ports):
    pid, cid = rig(client, unit, mode)
    _fill(client, pid, cid, box, body, n)
    before = client.get('/api/project').get_json()
    first = next(b for b in card_of(client, cid)['cvts']
                 if b['trunkIndex'] == 0)
    _ok(client.delete(f'/api/processors/{pid}/cvts/{first["id"]}'))
    card = card_of(client, cid)
    ids = {b['id'] for b in card['cvts']}
    backed = [b['backupOf'] for b in card['cvts'] if b['backupOf']]
    assert all(i in ids for i in backed)
    assert len(backed) == len(set(backed))
    _ok(client.put('/api/project', json=copy.deepcopy(before)))
    card = card_of(client, cid)
    assert pairs(card) == bound
    _counts_hold(card, ports)


# ── who picks the role ────────────────────────────────────────────────────

@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports',
                         [s for s in SHAPES if s[0] in PER_BOX],
                         ids=[i for i, s in zip(IDS, SHAPES)
                              if s[0] in PER_BOX])
def test_a_per_box_mirror_stays_a_mirror_and_backup_binds_again(
        client, unit, mode, other, box, body, n, bound, ports):
    """MCTRL R5 and MCTRL4K: a copy box set to Mirror feeds a mirror and
    backs nothing up; set back to Backup, it is bound again."""
    pid, cid = rig(client, unit, mode)
    _fill(client, pid, cid, box, body, n)
    copies = [b for b in card_of(client, cid)['cvts'] if b['copyRole']]
    assert copies and all(b['copyRoleChoice'] for b in copies)
    for b in copies:
        _ok(set_role(client, pid, b['id'], 'mirror'))
    card = card_of(client, cid)
    mine = {b['id']: b for b in card['cvts']}
    for b in copies:
        now = mine[b['id']]
        assert (now['copyRole'], now['backupOf']) == ('mirror', None), now
        assert now['mirrorOf'], now
    _counts_hold(card, ports)
    for b in copies:
        _ok(set_role(client, pid, b['id'], 'backup'))
    assert pairs(card_of(client, cid)) == bound


@pytest.mark.parametrize('unit,mode,role', [
    (VX400P, 'backup', 'backup'), (VX400P, 'copy', 'mirror'),
    (VX2000P, 'backup', 'backup'), (VX2000P, 'copy', 'mirror'),
    (M660P, None, 'backup'), (MX30, None, 'mirror'), (MX20, None, 'mirror'),
])
def test_a_unit_wide_role_is_not_picked_per_box(client, unit, mode, role):
    """Where the unit (or its sheet) sets the role, a copy box offers no
    choice and refuses one."""
    pid, cid = rig(client, unit, mode)
    _fill(client, pid, cid, CVT10, {},
          catalog.get_device(unit)['trunks'] // 2)
    copies = [b for b in card_of(client, cid)['cvts'] if b['copyRole']]
    assert copies and all(b['copyRole'] == role and not b['copyRoleChoice']
                          for b in copies)
    other = 'backup' if role == 'mirror' else 'mirror'
    resp = set_role(client, pid, copies[0]['id'], other)
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert 'per box' in resp.get_json()['error']


@pytest.mark.parametrize('unit,ports', [(MX30, 10), (MX20, 6)])
def test_the_mx30_and_mx20_copy_feeds_a_mirror(client, unit, ports):
    """"OPT 2 is the copy channel of OPT 1": the box there copies the box
    on OPT 1 for a mirror screen, its sockets past the unit's count, and
    the unit keeps its own count."""
    pid, cid = rig(client, unit)
    _fill(client, pid, cid, CVT10, {}, 1)
    card = card_of(client, cid)
    first, copy_box = sorted(card['cvts'], key=lambda b: b['trunkIndex'])
    assert (first['copyRole'], copy_box['copyRole']) == (None, 'mirror')
    assert copy_box['mirrorOf'] == first['id']
    assert copy_box['backupOf'] is None
    assert copy_box['firstPort'] == ports + 1
    assert card['copyTrunks'] == 'mirror'
    assert [t['role'] for t in card['copyTrunkList']] == ['mirror']
    _counts_hold(card, ports)


# ── shapes that differ are left alone ─────────────────────────────────────

@pytest.mark.parametrize('unit,mode', [(VX2000P, 'backup'), (M4K, None)],
                         ids=['vx2000-pro', 'mctrl4k'])
def test_a_copy_box_taking_other_opts_than_its_primaries_is_not_bound(
        client, unit, mode):
    """A CVT4K-S on OPT 3-4 behind two single-OPT boxes copies two boxes,
    not one: no pairing is guessed (the owner rules on these separately)."""
    pid, cid = rig(client, unit, mode)
    add_box(client, pid, cid, CVT10, pair=False)
    add_box(client, pid, cid, CVT10, pair=False)
    add_box(client, pid, cid, CVT4K, pair=False)
    last = card_of(client, cid)['cvts'][-1]
    assert last['copyRole'] == 'backup'
    assert last['trunksIn'] == 2
    assert last['backupOf'] is None


# ── the tray, the box cable sheet, the binder and the pull sheet ──────────

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

SEED_JS = """async ([unit, first, last, box, count]) => {
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
    const st = await send('/api/processors', 'POST', { deviceId: unit });
    const proc = st.processors[st.processors.length - 1];
    const card = proc.slots[0].card.id;
    if (first) {
        await send(`/api/processors/${proc.id}/cards/${card}`, 'PUT',
                   { mode: first });
    }
    for (let i = 0; i < count; i++) {
        await send(`/api/processors/${proc.id}/cards/${card}/cvts`, 'POST',
                   { deviceId: box, pair: false });
    }
    if (last) {
        await send(`/api/processors/${proc.id}/cards/${card}`, 'PUT',
                   { mode: last });
    }
    await window.app.refreshProcessors();
    return { proc: proc.id, card };
}"""

TRAY_JS = """(cardId) => {
    const app = window.app;
    const card = app._processorsResolved.flatMap(p => p.slots)
        .map(s => s.card).find(c => c && c.id === cardId);
    const fars = card.cvts.filter(b => b.backupOf);
    return fars.map(far => {
        const near = card.cvts.find(b => b.id === far.backupOf);
        const sec = document.querySelector(
            `[data-lrd-sec-id="hwdock-box-${near.id}"]`);
        const pair = app.fiberLoopPair(far);
        return {
            loop: !!sec && sec.classList.contains('hw-dock-loop'),
            farIsRow: !!sec && !!sec.querySelector('.hw-dock-loop-far'),
            farAlone: !!document.querySelector(
                `[data-lrd-sec-id="hwdock-box-${far.id}"]`),
            text: sec ? sec.textContent : '',
            fiberPair: !!pair && pair.near.id === near.id
                && pair.far.id === far.id,
        };
    }).concat([{ boxes: card.cvts.length,
                 pulled: app._pullAllBoxes()
                     .filter(e => e.card.id === cardId).length,
                 ceiling: card.ceiling,
                 mirrors: card.cvts.filter(b => b.copyRole === 'mirror'
                     && b.mirrorOf).length,
                 drawn: card.cvts.filter(b => document.querySelector(
                     `[data-lrd-sec-id="hwdock-box-${b.id}"]`)).length }]);
}"""

TRAY_CASES = [
    # (unit, mode before the boxes, mode after, box, boxes, loops,
    #  mirrors, ceiling)
    (VX400P, 'copy', 'backup', CVT10, 2, 1, 0, 4),
    (VX600P, 'copy', 'backup', CVT10, 2, 1, 0, 6),
    (VX1000P, 'copy', 'backup', CVT10, 2, 1, 0, 10),
    (VX2000P, 'copy', 'backup', CVT10, 4, 2, 0, 20),
    (VX2000P, 'backup', 'copy', CVT10, 4, 0, 2, 20),
    (M660P, None, None, CVT10, 2, 1, 0, 6),
    (R5, None, None, CVT10, 2, 1, 0, 8),
    (M4K, None, None, CVT4K, 2, 1, 0, 16),
    (MX30, None, None, CVT10, 2, 0, 1, 10),
    (MX20, None, None, CVT10, 2, 0, 1, 6),
]
TRAY_IDS = ['vx400-pro', 'vx600-pro', 'vx1000-pro', 'vx2000-pro',
            'vx2000-pro-copy', 'mctrl660-pro', 'mctrl-r5', 'mctrl4k', 'mx30',
            'mx20']


@pytest.mark.parametrize(
    'unit,first,last,box,count,nloops,nmirrors,ceiling', TRAY_CASES,
    ids=TRAY_IDS)
def test_the_tray_draws_each_backup_as_its_primarys_loop_end(
        e2e_server, pw_browser, unit, first, last, box, count, nloops,
        nmirrors, ceiling):
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
        ids = page.evaluate(SEED_JS, [unit, first, last, box, count])
        page.locator('[data-mode="data-flow"]').click()
        page.wait_for_function(
            "() => window.canvasRenderer.viewMode === 'data-flow'")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        *loops, totals = page.evaluate(TRAY_JS, ids['card'])
        assert len(loops) == nloops, loops
        for loop in loops:
            assert loop['loop'] and loop['farIsRow'], loop
            assert not loop['farAlone'], loop
            assert '(copy)' not in loop['text'], loop
            assert loop['fiberPair'], loop
        # every box is on the pull sheet and drawn in the tray (a loop's
        # far end as its near end's row), and no copy OPT added a port
        assert totals == {'boxes': count, 'pulled': count,
                          'ceiling': ceiling, 'mirrors': nmirrors,
                          'drawn': count - nloops}, totals
    finally:
        context.close()
