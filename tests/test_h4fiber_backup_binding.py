"""An H_4xfiber in Backup mode binds the box on OPT 3-4 to the box on OPT 1-2.

The owner, 2026-11-02: "I am trying to use the back up function with the
32-port card, but for some reason it is turning on copy". His H9 had two
H_4xfiber cards, each with two CVT4K-S boxes, set to Backup. The boxes were
put on before the mode was set (a new card starts in Independent, where a
box comes alone), so the box on OPT 3-4 carried no `backupOf`. The tray
then drew it as a box of its own, "CVT4K-S (copy)", with 16 sockets free.

NovaStar documents the mode: "OPT 3 serves as the backup of OPT 1, while
OPT 4 serves as the backup of OPT 2" (the catalog mode's copyTrunks
"backup"). The 2026-09-25 ruling: same-processor NovaStar backup pairs are
bound to their primary AUTOMATICALLY. So the binding is read off the mode
and the trunks on every resolve, whichever order the boxes and the mode
came in, and stored nowhere:

  * Backup: the box on a copy OPT backs up the box on the OPT it copies;
    the tray draws the two as one loop strip, never "(copy)";
  * Independent: no copy OPTs, so no box backs up another, even one that
    was added as a pair (its stored link waits for Backup to come back);
  * Copy: the copy OPTs feed a mirror screen, so the box there is a mirror.

Each box is still a box of its own on the paperwork (2026-09-25: NovaStar
in-unit port backup "feeds its OWN CVT at the far end"); only the way it
is presented and bound changes. The MX40 Pro's 20-port mode, where each box
picks Mirror or Backup, is untouched here.
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


H4 = 'novastar-card-h-4xfiber'
CVT4K = 'novastar-cvt4k-s'
CVT10 = 'novastar-cvt10'


def _ok(resp):
    assert resp.status_code in (200, 201), resp.get_data(as_text=True)
    return resp.get_json()


def rig(client, mode=None):
    """An H9 with an H_4xfiber in slot 0, in `mode` (None: as it starts)."""
    st = _ok(client.post('/api/processors', json={'deviceId': 'novastar-h9'}))
    pid = st['processors'][-1]['id']
    st = _ok(client.put(f'/api/processors/{pid}/slots/0',
                        json={'deviceId': H4}))
    cid = next(p for p in st['processors'] if p['id'] == pid
               )['slots'][0]['card']['id']
    if mode:
        set_mode(client, pid, cid, mode)
    return pid, cid


def set_mode(client, pid, cid, mode):
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': mode}))


def add_box(client, pid, cid, device=CVT4K, **body):
    return _ok(client.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                           json=dict({'deviceId': device}, **body)))


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


def shape(card):
    """Each box as (OPTs, first socket, role, which box it backs up)."""
    ids = {b['id']: i for i, b in enumerate(card['cvts'])}
    return [(b['trunkTitle'], b['firstPort'], b['copyRole'],
             ids.get(b['backupOf']))
            for b in card['cvts']]


BOUND = [('OPT 1-2', 1, None, None), ('OPT 3-4', 1, 'backup', 0)]
INDEPENDENT = [('OPT 1-2', 1, None, None), ('OPT 3-4', 17, None, None)]
MIRROR = [('OPT 1-2', 1, None, None), ('OPT 3-4', 17, 'mirror', None)]


# ── the order the boxes and the mode came in ──────────────────────────────

def test_a_new_card_starts_in_independent_where_a_box_comes_alone(client):
    pid, cid = rig(client)
    assert raw_card(client, cid)['mode'] == 'independent'
    add_box(client, pid, cid)
    assert len(card_of(client, cid)['cvts']) == 1


def test_boxes_put_on_before_backup_are_bound_once_backup_is_set(client):
    """The owner's order: two boxes on an Independent card, then Backup."""
    pid, cid = rig(client)
    add_box(client, pid, cid)
    add_box(client, pid, cid)
    assert shape(card_of(client, cid)) == INDEPENDENT
    set_mode(client, pid, cid, 'backup')
    assert shape(card_of(client, cid)) == BOUND
    # read off the mode, never written onto the record
    assert not any(b.get('backupOf') for b in raw_card(client, cid)['cvts'])


def test_backup_then_one_box_brings_its_bound_pair(client):
    pid, cid = rig(client, 'backup')
    add_box(client, pid, cid)
    assert shape(card_of(client, cid)) == BOUND


def test_backup_then_two_single_boxes_are_bound_too(client):
    """Declining the default pair declines the second box, not what the
    mode makes of a box somebody puts on OPT 3-4 afterwards."""
    pid, cid = rig(client, 'backup')
    add_box(client, pid, cid, pair=False)
    add_box(client, pid, cid, pair=False)
    assert shape(card_of(client, cid)) == BOUND


def test_a_saved_show_shaped_like_the_owners_opens_bound(client):
    """Two H_4xfiber cards in Backup, each with two CVT4K-S boxes that carry
    no backupOf, no copyRole and the default mode: as the owner's file."""
    proj = client.get('/api/project').get_json()
    proj['processors'] = [{
        'id': 'p-h9', 'deviceId': 'novastar-h9', 'name': 'H9',
        'redundancy': False, 'pairingsPerCard': True,
        'slots': [
            {'index': n, 'card': {
                'id': f'c{n}', 'deviceId': H4, 'mode': 'backup',
                'cvts': [{'id': f'c{n}-a', 'deviceId': CVT4K, 'name': '',
                          'mode': 'default'},
                         {'id': f'c{n}-b', 'deviceId': CVT4K, 'name': '',
                          'mode': 'default'}]}}
            for n in (0, 1)]}]
    _ok(client.put('/api/project', json=copy.deepcopy(proj)))
    for cid in ('c0', 'c1'):
        card = card_of(client, cid)
        assert shape(card) == BOUND
        # 16 sockets on the card, the bound box delivering the same 16 again
        assert [p['number'] for p in card['ports']] == list(range(1, 17))
        assert [p['number'] for p in card['cvts'][1]['ports']] \
            == list(range(1, 17))


# ── switching the mode ────────────────────────────────────────────────────

@pytest.mark.parametrize('made', ['pair', 'singles'])
def test_independent_unbinds_and_copy_makes_a_mirror(client, made):
    pid, cid = rig(client, 'backup')
    if made == 'pair':
        add_box(client, pid, cid)
    else:
        add_box(client, pid, cid, pair=False)
        add_box(client, pid, cid, pair=False)
    assert shape(card_of(client, cid)) == BOUND
    set_mode(client, pid, cid, 'independent')
    card = card_of(client, cid)
    assert shape(card) == INDEPENDENT
    assert [p['number'] for p in card['ports']] == list(range(1, 33))
    set_mode(client, pid, cid, 'copy')
    card = card_of(client, cid)
    assert shape(card) == MIRROR
    assert card['cvts'][1]['mirrorOf'] == card['cvts'][0]['id']
    set_mode(client, pid, cid, 'backup')
    assert shape(card_of(client, cid)) == BOUND


def test_undo_puts_the_binding_back_with_the_mode(client):
    """Undo restores the project as it was; the binding follows the mode
    it restores, with nothing of its own to restore."""
    pid, cid = rig(client)
    add_box(client, pid, cid)
    add_box(client, pid, cid)
    set_mode(client, pid, cid, 'backup')
    before = client.get('/api/project').get_json()
    set_mode(client, pid, cid, 'independent')
    assert shape(card_of(client, cid)) == INDEPENDENT
    _ok(client.put('/api/project', json=copy.deepcopy(before)))
    assert shape(card_of(client, cid)) == BOUND


def test_a_box_that_takes_other_trunks_than_its_primary_is_not_bound(client):
    """A CVT4K-S on OPT 3-4 copies two CVT10s, not one box: there is no
    single box it is, so it is left unbound rather than guessed."""
    pid, cid = rig(client, 'backup')
    add_box(client, pid, cid, CVT10, pair=False)
    add_box(client, pid, cid, CVT10, pair=False)
    add_box(client, pid, cid, CVT4K, pair=False)
    card = card_of(client, cid)
    assert [b['trunkTitle'] for b in card['cvts']] \
        == ['OPT 1', 'OPT 2', 'OPT 3-4']
    assert card['cvts'][2]['copyRole'] == 'backup'
    assert card['cvts'][2]['backupOf'] is None


def test_the_rule_reads_the_catalogs_backup_word_only():
    """Backup is the only mode word that binds; Copy feeds a mirror and the
    MX40 Pro's per-box mode is each box's own pick."""
    h4 = catalog.get_device(H4)
    assert catalog.copy_trunks(h4, 'backup') == 'backup'
    assert catalog.copy_trunks(h4, 'copy') == 'mirror'
    assert catalog.copy_trunks(h4, 'independent') is None


# ── the tray ──────────────────────────────────────────────────────────────

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

# The owner's order: two boxes on the card as it starts, then Backup.
SEED_JS = """async () => {
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
                          { deviceId: 'novastar-h9' });
    const proc = st.processors[st.processors.length - 1];
    const put = await send(`/api/processors/${proc.id}/slots/0`, 'PUT',
                           { deviceId: 'novastar-card-h-4xfiber' });
    const card = put.processors.find(p => p.id === proc.id).slots[0].card.id;
    for (let i = 0; i < 2; i++) {
        await send(`/api/processors/${proc.id}/cards/${card}/cvts`, 'POST',
                   { deviceId: 'novastar-cvt4k-s' });
    }
    await send(`/api/processors/${proc.id}/cards/${card}`, 'PUT',
               { mode: 'backup' });
    await window.app.refreshProcessors();
    return { proc: proc.id, card };
}"""

TRAY_JS = """(cardId) => {
    const card = window.app._processorsResolved.flatMap(p => p.slots)
        .map(s => s.card).find(c => c && c.id === cardId);
    const [near, far] = card.cvts;
    const sec = document.querySelector(
        `[data-lrd-sec-id="hwdock-box-${near.id}"]`);
    const unit = sec && sec.closest('.hw-dock-unit, .hw-dock-card')
        || document.body;
    return {
        loop: !!sec && sec.classList.contains('hw-dock-loop'),
        farIsRow: !!sec && !!sec.querySelector('.hw-dock-loop-far'),
        farAlone: !!document.querySelector(
            `[data-lrd-sec-id="hwdock-box-${far.id}"]`),
        text: (sec ? sec.textContent : '') + ' ' + unit.textContent,
    };
}"""


def test_the_tray_draws_the_bound_box_as_its_primarys_loop_end(
        e2e_server, pw_browser):
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
        ids = page.evaluate(SEED_JS)
        page.locator('[data-mode="data-flow"]').click()
        page.wait_for_function(
            "() => window.canvasRenderer.viewMode === 'data-flow'")
        page.evaluate("() => { window.__lrdQuiet = 0; }")
        page.wait_for_function(QUIET_JS)
        tray = page.evaluate(TRAY_JS, ids['card'])
        assert tray['loop'] and tray['farIsRow'], tray
        assert not tray['farAlone'], tray
        assert '(copy)' not in tray['text'], tray['text']
    finally:
        context.close()
