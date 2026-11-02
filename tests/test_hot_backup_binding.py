"""Every NovaStar copy OPT that backs up binds its box to the box it copies.

The owner, 2026-11-02, after the H_4xfiber fix: "We need to fix this for any
processor that supports hot backup like this. like the 8 port fiber card,
the enhanced one". The rule lives in resolve_card and reads the catalog
mode's copyTrunks only, so it reaches exactly the products whose entry
quotes a source for their copy OPTs:

  * H_4xfiber (enhanced), Backup (copyTrunks 'backup'): H15 Video Wall
    Splicer Specifications V1.15.0 p.37, "OPT 5 backs up or copies the
    output on OPT 1" (6 on 2, 7 on 3, 8 on 4);
  * MX40 Pro, 20-port (copyTrunks 'per-box'): User Manual V1.5.0 p.9, "OPT
    3 is the copy channel of OPT 1", each box there set to Mirror or Backup
    (owner, 2026-10-30);
  * NovaPro UHD (Specifications V1.2.0, "OPT 3 is the copy/hot backup
    channel for OPT 1") and NovaPro UHD Jr (Specifications V1.5.1, "OPT 3
    serves as the copy/hot backup for OPT 1"), per box Mirror or Backup the
    same way (owner, 2026-11-02).

A box on a copy OPT that backs up is the loop partner of the box on the OPT
it copies, whatever order the boxes and the mode came in, but only where the
two take exactly the same OPTs. A box set to Mirror feeds a mirror. The pair
stays two boxes on paper (2026-09-25: both counted, presented together), and
no copy OPT adds a port to the count.
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
UHD = 'novastar-novapro-uhd'
UHD_JR = 'novastar-novapro-uhd-jr'
CVT10 = 'novastar-cvt10'
CVT4K = 'novastar-cvt4k-s'


def _ok(resp):
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()


def rig(client, unit, mode=None):
    """A processor holding `unit` (a card in slot 0 of an H9, or the
    all-in-one itself), set to `mode` if given. Returns (pid, cid)."""
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


def add_box(client, pid, cid, device, **body):
    return _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                           json=dict({'deviceId': device}, **body)))


def set_role(client, pid, box_id, role):
    _ok(client.put(f'/api/processors/{pid}/cvts/{box_id}',
                   json={'copyRole': role}))


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
    """{OPTs of a box: OPTs of the box it backs up, or None}, plus the
    copy role, for every box, in OPT order."""
    title = {b['id']: b['trunkTitle'] for b in card['cvts']}
    return sorted((b['trunkTitle'], b['copyRole'], title.get(b['backupOf']))
                  for b in card['cvts'])


def primaries(card):
    return [p['number'] for p in card['ports'] if not p['mirrorOf']]


# Each card, the boxes that fit it, and what Backup makes of them.
# (unit, backup mode, other mode, box, add body, boxes per side, bound shape,
#  ports the card shows)
SHAPES = [
    (H4E, 'backup', 'copy', CVT10, {}, 4,
     [('OPT 1', None, None), ('OPT 2', None, None), ('OPT 3', None, None),
      ('OPT 4', None, None), ('OPT 5', 'backup', 'OPT 1'),
      ('OPT 6', 'backup', 'OPT 2'), ('OPT 7', 'backup', 'OPT 3'),
      ('OPT 8', 'backup', 'OPT 4')], 40),
    (H4E, 'backup', 'copy', CVT4K, {}, 2,
     [('OPT 1-2', None, None), ('OPT 3-4', None, None),
      ('OPT 5-6', 'backup', 'OPT 1-2'), ('OPT 7-8', 'backup', 'OPT 3-4')],
     32),
    (H4E, 'backup', 'copy', CVT4K, {'inputs': 1}, 4,
     [('OPT 1', None, None), ('OPT 2', None, None), ('OPT 3', None, None),
      ('OPT 4', None, None), ('OPT 5', 'backup', 'OPT 1'),
      ('OPT 6', 'backup', 'OPT 2'), ('OPT 7', 'backup', 'OPT 3'),
      ('OPT 8', 'backup', 'OPT 4')], 32),
    (MX40, '20-port', '40-port', CVT10, {}, 2,
     [('OPT 1', None, None), ('OPT 2', None, None),
      ('OPT 3', 'backup', 'OPT 1'), ('OPT 4', 'backup', 'OPT 2')], 20),
    (MX40, '20-port', '40-port', CVT4K, {}, 1,
     [('OPT 1-2', None, None), ('OPT 3-4', 'backup', 'OPT 1-2')], 20),
    (MX40, '20-port', '40-port', CVT4K, {'inputs': 1}, 2,
     [('OPT 1', None, None), ('OPT 2', None, None),
      ('OPT 3', 'backup', 'OPT 1'), ('OPT 4', 'backup', 'OPT 2')], 20),
] + [
    (unit, None, None, box, body, n, shape, 16)
    for unit in (UHD, UHD_JR)
    for box, body, n, shape in [
        (CVT10, {}, 2,
         [('OPT 1', None, None), ('OPT 2', None, None),
          ('OPT 3', 'backup', 'OPT 1'), ('OPT 4', 'backup', 'OPT 2')]),
        (CVT4K, {}, 1,
         [('OPT 1-2', None, None), ('OPT 3-4', 'backup', 'OPT 1-2')]),
        (CVT4K, {'inputs': 1}, 2,
         [('OPT 1', None, None), ('OPT 2', None, None),
          ('OPT 3', 'backup', 'OPT 1'), ('OPT 4', 'backup', 'OPT 2')]),
    ]
]
IDS = [f'{s[0].replace("novastar-", "")}-{s[3].replace("novastar-", "")}'
       f'{"-1opt" if s[4] else ""}' for s in SHAPES]


def _fill(client, pid, cid, box, body, n, **extra):
    for _ in range(n * 2):
        add_box(client, pid, cid, box, **dict(body, **extra))


def _counts_hold(card, ports):
    """The copies add no port: the card shows the same count bound or not."""
    assert card['ceiling'] == ports, card['ceiling']
    assert card['defined'] == ports, card['defined']
    assert len(primaries(card)) == ports


# ── the catalog ───────────────────────────────────────────────────────────

def test_the_uhds_quote_their_own_sheets_for_the_per_box_copy_opts():
    for unit, words in ((UHD, 'OPT 3 is the copy/hot backup channel for '
                              'OPT 1'),
                        (UHD_JR, 'OPT 3 serves as the copy/hot backup for '
                                 'OPT 1')):
        device = catalog.get_device(unit)
        assert catalog.copy_trunks(device, 'default') == 'per-box', unit
        assert words in device['copyTrunksNote'], unit
        # the OPTs still add no port
        assert device['trunkDelivery'] == 'copy'
        assert catalog.port_capacity(unit)['count'] == 16
    assert catalog.copy_trunks(catalog.get_device(H4E), 'backup') == 'backup'
    assert catalog.copy_trunks(catalog.get_device(MX40), '20-port') \
        == 'per-box'


# ── the order the boxes and the mode came in ──────────────────────────────

@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports', SHAPES,
                         ids=IDS)
def test_boxes_added_one_at_a_time_are_bound(client, unit, mode, other, box,
                                             body, n, bound, ports):
    """`pair: false` on every add: nothing stored, the binding is read off
    the mode and the OPTs."""
    pid, cid = rig(client, unit, mode)
    _fill(client, pid, cid, box, body, n, pair=False)
    card = card_of(client, cid)
    assert pairs(card) == bound
    _counts_hold(card, ports)
    assert not any(b.get('backupOf') for b in raw_card(client, cid)['cvts'])


@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports',
                         [s for s in SHAPES if s[2]],
                         ids=[i for i, s in zip(IDS, SHAPES) if s[2]])
def test_boxes_added_in_the_other_mode_are_bound_once_it_is_switched(
        client, unit, mode, other, box, body, n, bound, ports):
    """The owner's order: boxes on the card first (enhanced in Copy, MX40
    Pro in 40-port), the backup mode picked after."""
    pid, cid = rig(client, unit, other)
    _fill(client, pid, cid, box, body, n)
    assert not any(b['backupOf'] for b in card_of(client, cid)['cvts'])
    set_mode(client, pid, cid, mode)
    card = card_of(client, cid)
    assert pairs(card) == bound
    _counts_hold(card, ports)


@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports', SHAPES,
                         ids=IDS)
def test_a_normal_add_ends_bound(client, unit, mode, other, box, body, n,
                                 bound, ports):
    """The add as the tray sends it: NovaStar's default pair where the card
    makes one (enhanced, MX40 Pro), and on the UHDs, where a box comes
    alone, the copy boxes added after, as Backup."""
    pid, cid = rig(client, unit, mode)
    paired = catalog.default_backup_pair(raw_card(client, cid))
    assert paired == (unit not in (UHD, UHD_JR))
    for _ in range(n if paired else n * 2):
        add_box(client, pid, cid, box, **body)
    card = card_of(client, cid)
    assert pairs(card) == bound
    _counts_hold(card, ports)


@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports', SHAPES,
                         ids=IDS)
def test_deleting_a_primary_frees_its_partner_and_undo_binds_it_again(
        client, unit, mode, other, box, body, n, bound, ports):
    pid, cid = rig(client, unit, mode)
    _fill(client, pid, cid, box, body, n, pair=False)
    before = client.get('/api/project').get_json()
    first = next(b for b in card_of(client, cid)['cvts']
                 if b['trunkIndex'] == 0)
    _ok(client.delete(f'/api/processors/{pid}/cvts/{first["id"]}'))
    card = card_of(client, cid)
    ids = {b['id'] for b in card['cvts']}
    # nothing is bound to the box that went, and nothing is bound twice
    backed = [b['backupOf'] for b in card['cvts'] if b['backupOf']]
    assert all(i in ids for i in backed)
    assert len(backed) == len(set(backed))
    # undo (the whole-project PUT) brings the box back bound
    _ok(client.put('/api/project', json=copy.deepcopy(before)))
    card = card_of(client, cid)
    assert pairs(card) == bound
    _counts_hold(card, ports)


def test_the_enhanced_cards_partner_stays_on_its_opt_unbound_after_a_delete(
        client):
    """A box-fed card holds its OPTs: the OPT 5 box stays on OPT 5, backing
    up nothing, while OPT 6-8 stay bound."""
    pid, cid = rig(client, H4E, 'backup')
    _fill(client, pid, cid, CVT10, {}, 4, pair=False)
    first = next(b for b in card_of(client, cid)['cvts']
                 if b['trunkTitle'] == 'OPT 1')
    _ok(client.delete(f'/api/processors/{pid}/cvts/{first["id"]}'))
    assert pairs(card_of(client, cid)) == [
        ('OPT 2', None, None), ('OPT 3', None, None), ('OPT 4', None, None),
        ('OPT 5', 'backup', None), ('OPT 6', 'backup', 'OPT 2'),
        ('OPT 7', 'backup', 'OPT 3'), ('OPT 8', 'backup', 'OPT 4')]


# ── switching away and back ───────────────────────────────────────────────

@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports',
                         [s for s in SHAPES if s[2]],
                         ids=[i for i, s in zip(IDS, SHAPES) if s[2]])
def test_switching_the_mode_away_and_back(client, unit, mode, other, box,
                                          body, n, bound, ports):
    pid, cid = rig(client, unit, mode)
    _fill(client, pid, cid, box, body, n, pair=False)
    set_mode(client, pid, cid, other)
    card = card_of(client, cid)
    assert not any(b['backupOf'] for b in card['cvts'])
    if unit == H4E:
        # Copy: every copy box feeds a mirror of the box it copies
        assert all(b['copyRole'] == 'mirror' and b['mirrorOf']
                   for b in card['cvts'] if b['trunkIndex'] >= 4)
    set_mode(client, pid, cid, mode)
    assert pairs(card_of(client, cid)) == bound


@pytest.mark.parametrize('unit,mode,other,box,body,n,bound,ports',
                         [s for s in SHAPES if s[0] != H4E],
                         ids=[i for i, s in zip(IDS, SHAPES) if s[0] != H4E])
def test_a_per_box_mirror_stays_a_mirror_and_backup_binds_again(
        client, unit, mode, other, box, body, n, bound, ports):
    """MX40 Pro 20-port and the UHDs: a copy box set to Mirror feeds a
    mirror and backs nothing up; set back to Backup, it is bound again."""
    pid, cid = rig(client, unit, mode)
    _fill(client, pid, cid, box, body, n, pair=False)
    copies = [b for b in card_of(client, cid)['cvts'] if b['copyRole']]
    assert copies and all(b['copyRoleChoice'] for b in copies)
    for b in copies:
        set_role(client, pid, b['id'], 'mirror')
    card = card_of(client, cid)
    mine = {b['id']: b for b in card['cvts']}
    for b in copies:
        now = mine[b['id']]
        assert (now['copyRole'], now['backupOf']) == ('mirror', None), now
        assert now['mirrorOf'], now
    _counts_hold(card, ports)
    for b in copies:
        set_role(client, pid, b['id'], 'backup')
    assert pairs(card_of(client, cid)) == bound


# ── shapes that differ are left alone ─────────────────────────────────────

@pytest.mark.parametrize('unit,mode,firsts,copy_box', [
    (H4E, 'backup', [CVT10] * 4, CVT4K),
    (MX40, '20-port', [CVT10] * 2, CVT4K),
    (UHD_JR, None, [CVT10] * 2, CVT4K),
    (UHD, None, [CVT10] * 2, CVT4K),
], ids=['h4e', 'mx40', 'uhd-jr', 'uhd'])
def test_a_copy_box_taking_other_opts_than_its_primaries_is_not_bound(
        client, unit, mode, firsts, copy_box):
    """A CVT4K-S on two copy OPTs behind two single-OPT boxes copies two
    boxes, not one: no pairing is guessed."""
    pid, cid = rig(client, unit, mode)
    for box in firsts:
        add_box(client, pid, cid, box, pair=False)
    add_box(client, pid, cid, copy_box, pair=False)
    card = card_of(client, cid)
    last = card['cvts'][-1]
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

# Boxes added one at a time (pair: false) with the mode set after, so the
# binding the tray draws can only have come from resolve_card.
SEED_JS = """async ([unit, kind, first, last, box, count]) => {
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
            near: near.trunkTitle,
            far: far.trunkTitle,
            loop: !!sec && sec.classList.contains('hw-dock-loop'),
            farIsRow: !!sec && !!sec.querySelector('.hw-dock-loop-far'),
            farAlone: !!document.querySelector(
                `[data-lrd-sec-id="hwdock-box-${far.id}"]`),
            text: sec ? sec.textContent : '',
            // the box cable sheet and the binder's fiber tables read the
            // pair off this one helper
            fiberPair: !!pair && pair.near.id === near.id
                && pair.far.id === far.id,
        };
    }).concat([{ boxes: card.cvts.length,
                 pulled: app._pullAllBoxes()
                     .filter(e => e.card.id === cardId).length,
                 ceiling: card.ceiling }]);
}"""

TRAY_CASES = [
    # (unit, kind, mode before the boxes, mode after, box, boxes, pairs,
    #  ceiling)
    (H4E, 'card', 'copy', 'backup', CVT10, 8, 4, 40),
    (MX40, 'unit', '40-port', '20-port', CVT10, 4, 2, 20),
    (UHD, 'unit', None, None, CVT4K, 2, 1, 16),
    (UHD_JR, 'unit', None, None, CVT4K, 2, 1, 16),
]


@pytest.mark.parametrize('unit,kind,first,last,box,count,npairs,ceiling',
                         TRAY_CASES, ids=['h4e', 'mx40', 'uhd', 'uhd-jr'])
def test_the_tray_draws_each_backup_as_its_primarys_loop_end(
        e2e_server, pw_browser, unit, kind, first, last, box, count, npairs,
        ceiling):
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
        ids = page.evaluate(SEED_JS, [unit, kind, first, last, box, count])
        page.locator('[data-mode="data-flow"]').click()
        page.wait_for_function(
            "() => window.canvasRenderer.viewMode === 'data-flow'")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        *loops, totals = page.evaluate(TRAY_JS, ids['card'])
        assert len(loops) == npairs, loops
        for loop in loops:
            assert loop['loop'] and loop['farIsRow'], loop
            assert not loop['farAlone'], loop
            assert '(copy)' not in loop['text'], loop
            assert loop['fiberPair'], loop
        # both boxes of every loop are on the pull sheet, and no copy OPT
        # added a port
        assert totals == {'boxes': count, 'pulled': count,
                          'ceiling': ceiling}, totals
    finally:
        context.close()
