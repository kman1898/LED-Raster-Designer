"""A mirror whose feed is gone never leaves a screen stuck, and a backup box
says what it backs up.

Owner, 2026-11-01: "If the card is unplugged from the FIRST (source) screen,
the copy screen unplugs too." and "Unplugging the copy alone just removes the
copy." A locked screen stays unchanged until unlocked. QA of 1.6.0 beta.6
found the second screen left mirroring with nothing plugged in and no way out:
Remove processor and Remove card took the source's feed without the unplug,
and Remove box on the Mirror box, a box set to Backup and a card out of Copy
took the copy's. The drop was refused with "unplug the card from Screen2", and
nothing was plugged in to unplug.

Now:

* A Remove that takes the source's feed lets the mirror go, in the same undo
  step (routes_processors _let_mirrors_go).
* A Remove that takes the copy's LAST socket unplugs the copy, so it goes too.
  A copy with sockets left keeps them.
* A setting that leaves the copy nothing to ride (Backup, a mode) keeps the
  mirror: the rulings speak of unplugging, and the tray's line names the
  setting that brings it back. The line offers Stop mirroring, and the
  refusal says so instead of "unplug the card".
* A mirror kept by its lock has the same line once it is unlocked.

The other half: a Backup box dropped on a screen on the unit's own ports says
its backup already rides on the box, as it does behind a primary box, and
never sends the person to clear a working screen.

Fiber extensions naming their mode are in tests/test_fiber_extension_mode.py.

Run locally:
    python -m pytest tests/test_mirror_feed_gone.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_copy_mode import (  # noqa: E402
    CVT10, H4, _ok, add_boxes, card_of, mirror_rig, pin, resolve, scr_of,
    screen, set_mirror, slot_card, h9)
from test_mirror_box_drop import (  # noqa: E402
    BOXES_JS, PILL_JS, STATE_JS, STATUS_JS, TOASTS_JS, box_key, drag, seed)


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the rules, through the routes ─────────────────────────────────────────

def _layer(client, layer_id):
    return next(l for l in client.get('/api/project').get_json()['layers']
                if l['id'] == layer_id)


def _issue(res, layer_id):
    return next((i for i in res['issues'] if i['layerId'] == str(layer_id)
                 and i['kind'].startswith('mirror-')), None)


def _stopped(client, body, b):
    assert body['mirrorsCleared'] == [b], body.get('mirrorsCleared')
    assert 'dataMirrorOf' not in _layer(client, b)


def _kept(client, body, b, a):
    assert 'mirrorsCleared' not in body
    assert _layer(client, b)['dataMirrorOf'] == a


def test_remove_processor_takes_the_mirror_with_the_source(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    body = _ok(client.delete(f'/api/processors/{pid}'))
    _stopped(client, body, b)
    assert body['note'].endswith(
        '3 ports of SL are unplaced again, and SR no longer mirrors SL')
    assert scr_of(resolve(client, screens), b)['mirrorOf'] is None


def test_remove_card_and_a_new_card_in_the_slot_take_the_mirror(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    _stopped(client, _ok(client.put(f'/api/processors/{pid}/slots/0',
                                    json={'deviceId': None})), b)
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    _stopped(client, _ok(client.put(f'/api/processors/{pid}/slots/0',
                                    json={'deviceId': H4})), b)


def test_remove_of_another_card_leaves_the_mirror(client):
    pid, cid, a, b, screens = mirror_rig(client)
    other = slot_card(client, pid, 1, H4, 'copy')
    set_mirror(client, b, a)
    _kept(client, _ok(client.put(f'/api/processors/{pid}/slots/1',
                                 json={'deviceId': None})), b, a)
    assert [p['port'] for p in scr_of(resolve(client, screens), b)['ports']] \
        == [17, 18, 19]
    assert other not in [p['cardId'] for p
                         in scr_of(resolve(client, screens), b)['ports']]


def test_a_source_left_on_a_second_card_keeps_its_mirror(client):
    """Part of the source goes with the card, part stays: the rule for a
    released port, so the copy keeps the ports it still has."""
    pid, cid, a, b, screens = mirror_rig(client)
    other = slot_card(client, pid, 1, H4, 'copy')
    add_boxes(client, pid, other, 4)
    _ok(pin(client, screens, a, 0, other, 1))
    set_mirror(client, b, a)
    _kept(client, _ok(client.put(f'/api/processors/{pid}/slots/0',
                                 json={'deviceId': None})), b, a)
    sr = scr_of(resolve(client, screens), b)
    assert [(p['cardId'], p['port']) for p in sr['ports']] \
        == [(other, 17), (None, None), (None, None)]


def test_a_locked_mirror_stays_and_its_line_is_the_way_out(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    _ok(client.put(f'/api/layer/{b}', json={'locked': True}))
    _kept(client, _ok(client.delete(f'/api/processors/{pid}')), b, a)
    sent = [dict(s, mirrorOf=str(a)) if s['layerId'] == str(b) else s
            for s in screens]
    issue = _issue(resolve(client, sent), b)
    assert issue['kind'] == 'mirror-source-unplaced'
    assert issue['message'] == ('SR mirrors SL, but SL is not on a processor, '
                                'so SR has nowhere to plug in.')
    assert issue['offers'] == [{'action': 'release', 'layerId': str(b),
                                'label': 'Stop mirroring'}]
    _ok(client.put(f'/api/layer/{b}', json={'locked': False}))
    _stopped(client, _ok(client.post('/api/port-assignments/unpin', json={
        'screens': sent, 'layerId': str(b)})), b)


def test_the_primary_box_going_with_the_source_takes_the_mirror(client):
    """A box-fed card: the source's sockets go with their box."""
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    first = card_of(client, cid)['cvts'][0]['id']
    _stopped(client, _ok(client.delete(f'/api/processors/{pid}/cvts/{first}')),
             b)


def test_the_mirror_box_going_unplugs_the_copy_and_keeps_the_source(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    box = card_of(client, cid)['cvts'][2]
    assert box['trunkTitle'] == 'OPT 3'
    body = _ok(client.delete(f'/api/processors/{pid}/cvts/{box["id"]}'))
    _stopped(client, body, b)
    assert body['note'] == (f'Removed box {box["displayTitle"]}: SR no longer '
                            f'mirrors SL')
    assert 'portAssignments' not in body
    res = resolve(client, screens)
    assert [p['port'] for p in scr_of(res, a)['ports']] == [1, 2, 3]
    assert scr_of(res, b)['unplaced'] == [0, 1, 2]


def test_a_copy_with_a_socket_left_keeps_it_and_says_what_is_missing(client):
    """Ports on OPT 1 and OPT 2, so the copy rides OPT 3 and OPT 4: one of
    them gone is part of the copy, not the copy. Its other half stands."""
    pid, cid, a, b, screens = mirror_rig(client)
    _ok(pin(client, screens, a, 2, cid, 11))
    set_mirror(client, b, a)
    sent = [dict(s, mirrorOf=str(a)) if s['layerId'] == str(b) else s
            for s in screens]
    box = card_of(client, cid)['cvts'][3]
    assert box['trunkTitle'] == 'OPT 4'
    _kept(client, _ok(client.delete(f'/api/processors/{pid}/cvts/{box["id"]}')),
          b, a)
    res = resolve(client, sent)
    assert [p['port'] for p in scr_of(res, b)['ports']] == [17, 18, None]
    issue = _issue(res, b)
    assert 'has no box (it copies OPT 2)' in issue['message'], issue
    assert [o['label'] for o in issue['offers']] == ['Stop mirroring']


def test_a_locked_mirror_keeps_its_place_when_its_box_goes(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    _ok(client.put(f'/api/layer/{b}', json={'locked': True}))
    box = card_of(client, cid)['cvts'][2]['id']
    _kept(client, _ok(client.delete(f'/api/processors/{pid}/cvts/{box}')), b, a)


def test_a_box_nothing_rides_going_changes_no_mirror(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    box = card_of(client, cid)['cvts'][3]['id']
    _kept(client, _ok(client.delete(f'/api/processors/{pid}/cvts/{box}')), b, a)


@pytest.mark.parametrize('mode,needle', [
    ('backup', 'is in Backup mode. Set it to Copy mode to feed a mirror '
               'screen.'),
    ('independent', 'is in Independent mode. Set it to Copy mode to feed a '
                    'mirror screen.'),
])
def test_a_mode_change_keeps_the_mirror_and_offers_the_way_out(client, mode,
                                                               needle):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    sent = [dict(s, mirrorOf=str(a)) if s['layerId'] == str(b) else s
            for s in screens]
    _kept(client, _ok(client.put(f'/api/processors/{pid}/cards/{cid}',
                                 json={'mode': mode})), b, a)
    res = resolve(client, sent)
    issue = _issue(res, b)
    assert needle in issue['message'], issue
    assert [o['label'] for o in issue['offers']] == ['Stop mirroring']
    # the setting brings it back, as the line says
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': 'copy'}))
    assert [p['port'] for p in scr_of(resolve(client, sent), b)['ports']] \
        == [17, 18, 19]


def test_a_source_unplugged_from_a_card_out_of_copy_takes_the_mirror(client):
    """The card left Copy, so the source was on no copy card, and the unplug
    used to miss the mirror and leave it stuck."""
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': 'backup'}))
    _stopped(client, _ok(client.post('/api/port-assignments/unpin', json={
        'screens': screens, 'layerId': str(a)})), b)


def test_the_refusal_says_unplug_only_where_something_is_plugged_in(client):
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    sent = [dict(s, mirrorOf=str(a)) if s['layerId'] == str(b) else s
            for s in screens]
    landed = pin(client, sent, b, 0, cid, 9)
    assert landed.status_code == 409
    assert landed.get_json()['error'].endswith(
        'or unplug the card from SR to stop mirroring.')
    _ok(client.put(f'/api/processors/{pid}/cards/{cid}', json={'mode': 'backup'}))
    bare = pin(client, sent, b, 0, cid, 9)
    assert bare.status_code == 409
    error = bare.get_json()['error']
    assert 'unplug the card' not in error, error
    assert error.endswith('Nothing is plugged into SR to unplug: press Stop '
                          'mirroring on its line in the tray.'), error


def test_a_show_saved_in_the_trap_opens_with_its_way_out(client):
    """A beta.6 file: the mirror with no feed, its source unplugged."""
    pid, cid, a, b, screens = mirror_rig(client)
    set_mirror(client, b, a)
    saved = client.get('/api/project').get_json()
    saved['port_assignments']['pins'] = []
    saved['processors'] = []
    _ok(client.post('/api/project/new', json={}), (200, 201))
    _ok(client.put('/api/project', json=saved), 200)
    assert _layer(client, b)['dataMirrorOf'] == a
    sent = [dict(s, mirrorOf=str(a)) if s['layerId'] == str(b) else s
            for s in screens]
    res = resolve(client, sent)
    assert res['configured'] is False
    assert _issue(res, b)['offers'][0]['label'] == 'Stop mirroring'


# ── the gestures, with a real pointer ─────────────────────────────────────

@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()

    # No real dialog on the desktop. The open answers "unavailable", so the
    # page takes its own file input.
    def answer(body):
        return lambda r: r.fulfill(status=200, content_type='application/json',
                                   body=body)

    for kind, body in (('save-file', '{"cancelled": true, "path": null}'),
                       ('select-directory', '{"cancelled": true, "path": null}'),
                       ('open-file', '{"ok": false, "cancelled": false}')):
        pg.route(f'**/api/native-dialog/{kind}', answer(body))
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => window.app && window.app._initialLoadComplete === true",
        timeout=20000)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    pg.evaluate(TOASTS_JS)
    yield pg, errors
    context.close()


ISSUES_JS = """() => [...document.querySelectorAll('#hw-dock-issues .hw-dock-issue')]
    .map(row => ({text: row.querySelector('.hw-dock-issue-msg').textContent,
                  buttons: [...row.querySelectorAll('button')]
                      .map(b => b.textContent)}))"""


def _mirrored(pg):
    """Screen1 on box A-B and Screen2 its copy on Mirror box C-D, both made
    by dragging. A fresh history."""
    ids = seed(pg, 'api-mirror')
    boxes = pg.evaluate(BOXES_JS, ids['cid'])
    assert drag(pg, box_key(pg, boxes[0]['id']), ids['s1'])['text'] == '2 ports'
    assert drag(pg, box_key(pg, boxes[1]['id']), ids['s2'])['text'] \
        == 'Copy of Screen1'
    pg.evaluate("() => window.app.resetHistory('Mirror Rig')")
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] == ids['s1'], st
    pg.evaluate(TOASTS_JS)
    return ids, boxes


def _gear_remove(pg, pop):
    pg.locator(f'[data-hwpop="{pop}"]').first.click()
    pg.wait_for_selector('#hw-gear-popover .hw-pop-remove')
    pg.locator('#hw-gear-popover .hw-pop-remove').click()
    pg.wait_for_timeout(1000)


def _undo(pg, verb='undo'):
    pg.evaluate(f"() => window.app.{verb}()")
    pg.wait_for_timeout(900)
    pg.evaluate("() => window.app.refreshPortAssignment()")
    pg.wait_for_timeout(300)


def _add_unit(pg):
    """A new UHD Jr off the tray's picker's route."""
    unit = pg.evaluate("""async () => {
        const app = window.app;
        await app._processorRequest('/api/processors', 'POST',
            {deviceId: 'novastar-novapro-uhd-jr'}, 'Add Processor');
        await app.refreshPortAssignment();
        app.renderHardwareDock();
        const p = app._processorsResolved[app._processorsResolved.length - 1];
        return {pid: p.id, cid: p.slots[0].card.id};
    }""")
    pg.wait_for_timeout(500)
    return unit


def _open_as_saved(pg, tmp_path, name):
    """What the Save button writes, opened through the page's own file input."""
    saved = pg.evaluate("() => JSON.parse(window.app.serializeProjectForFile())")
    saved['name'] = name
    path = tmp_path / f'{name}.json'
    path.write_text(json.dumps(saved), encoding='utf-8')
    with pg.expect_file_chooser() as chooser:
        pg.evaluate("window.app.loadProjectFromFile()")
    chooser.value.set_files(str(path))
    pg.wait_for_function(
        f"() => window.app.project && window.app.project.name === {json.dumps(name)}",
        timeout=10000)
    pg.wait_for_timeout(1000)
    pg.evaluate("""async () => {
        const r = window.canvasRenderer;
        r.zoom = 0.3; r.panX = 60; r.panY = 40; r.render();
        await window.app.refreshPortAssignment();
    }""")
    pg.wait_for_timeout(300)


def test_remove_processor_frees_the_second_screen_in_one_undo_step(page, tmp_path):
    pg, errors = page
    ids, boxes = _mirrored(pg)
    before = pg.evaluate(STATE_JS, ids)['history']
    _gear_remove(pg, f"proc-{ids['pid']}")
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None and st['serverMirrorOf'] is None, st
    assert st['history'] == before + 1 and st['last'] == 'Remove Processor', st
    assert st['serverPins'] == [] and st['pins'] == [], st
    toasts = pg.evaluate(TOASTS_JS)
    assert [t['msg'] for t in toasts] == [
        'Removed NovaPro UHD Jr: 2 ports of Screen1 are unplaced again, and '
        'Screen2 no longer mirrors Screen1'], toasts

    # one undo: the processor, its pins and the mirror, server included
    _undo(pg)
    back = pg.evaluate(STATE_JS, ids)
    assert back['mirrorOf'] == ids['s1'] and back['serverMirrorOf'] == ids['s1']
    assert back['s1'] == [[1, 'pin'], [2, 'pin']], back
    assert back['s2'] == [[17, 'mirror'], [18, 'mirror']], back
    _undo(pg, 'redo')
    again = pg.evaluate(STATE_JS, ids)
    assert again['mirrorOf'] is None and again['serverMirrorOf'] is None, again
    assert again['serverPins'] == [], again

    # the owner's next gesture: a new UHD Jr dragged onto Screen2 lands
    unit = _add_unit(pg)
    pill = drag(pg, f"card-{unit['cid']}", ids['s2'])
    assert pill == {'text': '2 ports', 'bad': False}, pill
    st = pg.evaluate(STATE_JS, ids)
    assert st['s2'] == [[1, 'pin'], [2, 'pin']], st

    # and it stays that way through a save and a reopen
    _open_as_saved(pg, tmp_path, 'MirrorGoneProc')
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None and st['serverMirrorOf'] is None, st
    assert st['s2'] == [[1, 'pin'], [2, 'pin']], st
    assert errors == []


def test_remove_box_on_the_mirror_box_frees_the_copy_and_keeps_the_source(page, tmp_path):
    pg, errors = page
    ids, boxes = _mirrored(pg)
    before = pg.evaluate(STATE_JS, ids)['history']
    _gear_remove(pg, f"box-{boxes[1]['id']}")
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None and st['serverMirrorOf'] is None, st
    assert st['s1'] == [[1, 'pin'], [2, 'pin']], st
    assert st['s2'] == [[None, None], [None, None]], st
    assert st['history'] == before + 1, st
    assert st['last'] == 'Remove Breakout Box', st
    assert [t['msg'] for t in pg.evaluate(TOASTS_JS)] == [
        'Removed box CVT4K-S C-D: Screen2 no longer mirrors Screen1']
    assert not [r for r in pg.evaluate(ISSUES_JS) if 'mirrors' in r['text']]

    _undo(pg)
    back = pg.evaluate(STATE_JS, ids)
    assert back['mirrorOf'] == ids['s1'] and back['serverMirrorOf'] == ids['s1']
    assert back['s2'] == [[17, 'mirror'], [18, 'mirror']], back
    assert [b['title'] for b in pg.evaluate(BOXES_JS, ids['cid'])] \
        == ['CVT4K-S A-B', 'CVT4K-S C-D']
    _undo(pg, 'redo')
    again = pg.evaluate(STATE_JS, ids)
    assert again['mirrorOf'] is None and again['serverMirrorOf'] is None, again
    assert again['s1'] == [[1, 'pin'], [2, 'pin']], again

    # Screen2 is its own screen: the unit's next free ports take it
    pill = drag(pg, f"card-{ids['cid']}", ids['s2'])
    assert pill == {'text': '2 ports', 'bad': False}, pill
    st = pg.evaluate(STATE_JS, ids)
    assert st['s2'] == [[3, 'pin'], [4, 'pin']], st
    _open_as_saved(pg, tmp_path, 'MirrorGoneBox')
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None, st
    assert st['s2'] == [[3, 'pin'], [4, 'pin']], st
    assert errors == []


def test_a_box_set_to_backup_keeps_the_mirror_and_says_the_way_out(page, tmp_path):
    pg, errors = page
    ids, boxes = _mirrored(pg)
    mirror = boxes[1]['id']
    pg.locator(f'[data-hwpop="box-{mirror}"]').first.click()
    pg.locator(f'[data-lrd-field="processor-cvt-copyrole-{mirror}"] '
               '[data-level="backup"]').click()
    pg.wait_for_timeout(1000)
    pg.keyboard.press('Escape')
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] == ids['s1'], st
    assert st['s2'] == [[None, None], [None, None]], st
    rows = [r for r in pg.evaluate(ISSUES_JS) if 'Screen2 mirrors' in r['text']]
    assert rows == [{
        'text': 'Screen2 mirrors Screen1, but the box on OPT 3 of NovaPro UHD '
                'Jr is set to Backup. Set it to Mirror to feed a mirror '
                'screen. Screen2 ports 1-2 have nowhere to plug in.',
        'buttons': ['Stop mirroring']}], rows

    # a card dropped on it is refused in true words, before and at the release
    unit = _add_unit(pg)
    pill = drag(pg, f"card-{unit['cid']}", ids['s2'])
    want = ("Screen2 mirrors Screen1. Its data port map follows Screen1's and "
            "cannot be changed on its own. Nothing is plugged into Screen2 to "
            "unplug: press Stop mirroring on its line in the tray.")
    assert pill == {'text': want, 'bad': True}, pill
    assert [t['msg'] for t in pg.evaluate(TOASTS_JS) if t['err']] == [want]

    # survives a save and a reopen, line and all
    _open_as_saved(pg, tmp_path, 'MirrorOnBackup')
    assert pg.evaluate(STATE_JS, ids)['mirrorOf'] == ids['s1']
    assert [r['buttons'] for r in pg.evaluate(ISSUES_JS)
            if 'Screen2 mirrors' in r['text']] == [['Stop mirroring']]

    # the button lets it go, as one step; undo brings it back, redo frees it
    pg.evaluate("() => window.app.resetHistory('Mirror Rig')")
    pg.locator('#hw-dock-issues button', has_text='Stop mirroring').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None and st['serverMirrorOf'] is None, st
    assert not [r for r in pg.evaluate(ISSUES_JS) if 'Screen2 mirrors' in r['text']]
    _undo(pg)
    assert pg.evaluate(STATE_JS, ids)['serverMirrorOf'] == ids['s1']
    _undo(pg, 'redo')
    assert pg.evaluate(STATE_JS, ids)['serverMirrorOf'] is None
    pill = drag(pg, f"card-{unit['cid']}", ids['s2'])
    assert pill == {'text': '2 ports', 'bad': False}, pill
    assert pg.evaluate(STATE_JS, ids)['s2'] == [[1, 'pin'], [2, 'pin']]
    assert errors == []


def test_the_box_set_back_to_mirror_brings_the_copy_back(page):
    pg, errors = page
    ids, boxes = _mirrored(pg)
    mirror = boxes[1]['id']
    pg.locator(f'[data-hwpop="box-{mirror}"]').first.click()
    seg = f'[data-lrd-field="processor-cvt-copyrole-{mirror}"] '
    pg.locator(seg + '[data-level="backup"]').click()
    pg.wait_for_timeout(1000)
    assert pg.evaluate(STATE_JS, ids)['s2'] == [[None, None], [None, None]]
    pg.locator(seg + '[data-level="mirror"]').click()
    pg.wait_for_timeout(1000)
    pg.keyboard.press('Escape')
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] == ids['s1'], st
    assert st['s2'] == [[17, 'mirror'], [18, 'mirror']], st
    assert errors == []


def test_a_locked_copy_stays_then_stops_mirroring_once_unlocked(page, tmp_path):
    """Remove processor with Screen2 locked: Screen2 is left as it was. With
    no processor left the tray still carries its line, and unlocked the
    button frees it. Locked, it says so."""
    pg, errors = page
    ids, boxes = _mirrored(pg)

    def lock(on):
        pg.evaluate("""async ([id, on]) => {
            const app = window.app;
            await fetch(`/api/layer/${id}`, {method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({locked: on})});
            app.project.layers.find(l => l.id === id).locked = on;
        }""", [ids['s2'], on])

    lock(True)
    _gear_remove(pg, f"proc-{ids['pid']}")
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] == ids['s1'] and st['serverMirrorOf'] == ids['s1'], st
    assert [t['msg'] for t in pg.evaluate(TOASTS_JS)] == [
        'Removed NovaPro UHD Jr: 2 ports of Screen1 are unplaced again']
    pg.evaluate("() => window.app.renderPortAssignmentPanel()")
    rows = [r for r in pg.evaluate(ISSUES_JS) if 'Screen2 mirrors' in r['text']]
    assert rows == [{'text': 'Screen2 mirrors Screen1, but Screen1 is not on a '
                             'processor, so Screen2 has nowhere to plug in.',
                     'buttons': ['Stop mirroring']}], rows
    pg.locator('#hw-dock-issues button', has_text='Stop mirroring').click()
    pg.wait_for_timeout(600)
    assert pg.evaluate(STATE_JS, ids)['serverMirrorOf'] == ids['s1']
    pg.keyboard.press('Escape')
    lock(False)
    _open_as_saved(pg, tmp_path, 'MirrorLockedThenFreed')
    pg.locator('#hw-dock-issues button', has_text='Stop mirroring').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None and st['serverMirrorOf'] is None, st
    assert errors == []


H4_SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments; delete proj.fiberCables;
    delete proj.snakes;
    await j('PUT', '/api/project', proj);
    const made = [];
    for (const [n, x] of [['Screen1', 0], ['Screen2', 1500]]) {
        const l = await j('POST', '/api/layer/add', {name: n, columns: 10,
            rows: 5, cabinet_width: 128, cabinet_height: 128, offset_x: x,
            offset_y: 0});
        await j('PUT', `/api/layer/${l.id}`, {processorType: 'novastar-armor',
                                              bitDepth: 8, frameRate: 60});
        made.push(l.id);
    }
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.resolved[st.resolved.length - 1].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`,
                 {deviceId: 'novastar-card-h-4xfiber'});
    const cid = st.resolved[st.resolved.length - 1].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cid}`, {mode: 'copy'});
    for (let i = 0; i < 4; i++) {
        await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`,
                {deviceId: 'novastar-cvt10', pair: false});
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.currentLayer = app.project.layers[0];
    app.selectedLayerIds = new Set([app.project.layers[0].id]);
    await app.refreshProcessors();
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.3; r.panX = 60; r.panY = 40; r.render();
    await app.refreshPortAssignment();
    app.renderHardwareDock();
    app.resetHistory('H4 Seed');
    return {pid, cid, s1: made[0], s2: made[1]};
}"""


def _h4_mirrored(pg):
    ids = pg.evaluate(H4_SEED_JS)
    pg.wait_for_timeout(500)
    assert drag(pg, f"card-{ids['cid']}", ids['s1'])['text'] == '2 ports'
    assert drag(pg, f"card-{ids['cid']}", ids['s2'])['text'] == 'Copy of Screen1'
    pg.evaluate("() => window.app.resetHistory('Mirror Rig')")
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] == ids['s1'], st
    pg.evaluate(TOASTS_JS)
    return ids


def test_remove_card_on_an_h_series_frees_the_copy_in_one_step(page):
    pg, errors = page
    ids = _h4_mirrored(pg)
    before = pg.evaluate(STATE_JS, ids)['history']
    _gear_remove(pg, f"card-{ids['cid']}")
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None and st['serverMirrorOf'] is None, st
    assert st['history'] == before + 1, st
    _undo(pg)
    back = pg.evaluate(STATE_JS, ids)
    assert back['mirrorOf'] == ids['s1'] and back['serverMirrorOf'] == ids['s1']
    assert back['s2'] == [[17, 'mirror'], [18, 'mirror']], back
    _undo(pg, 'redo')
    assert pg.evaluate(STATE_JS, ids)['serverMirrorOf'] is None
    assert errors == []


@pytest.mark.parametrize('mode,word', [('backup', 'Backup'),
                                       ('independent', 'Independent')])
def test_a_card_out_of_copy_keeps_the_mirror_and_offers_the_way_out(page, mode, word):
    pg, errors = page
    ids = _h4_mirrored(pg)
    pg.locator(f'[data-hwpop="card-{ids["cid"]}"]').first.click()
    pg.locator(f'[data-lrd-field="processor-card-mode-{ids["cid"]}"]') \
        .select_option(mode)
    pg.wait_for_timeout(1000)
    pg.keyboard.press('Escape')
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] == ids['s1'], st
    rows = [r for r in pg.evaluate(ISSUES_JS) if 'Screen2 mirrors' in r['text']]
    assert len(rows) == 1 and f'is in {word} mode.' in rows[0]['text'], rows
    assert rows[0]['buttons'] == ['Stop mirroring'], rows
    pg.locator('#hw-dock-issues button', has_text='Stop mirroring').click()
    pg.wait_for_timeout(900)
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None and st['serverMirrorOf'] is None, st
    assert st['s1'] == [[1, 'pin'], [2, 'pin']], st
    assert errors == []


# ── a backup box on a screen already on what it backs up ──────────────────

UNIT_SEED_JS = """async ([device, mode, boxes, platform]) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments; delete proj.fiberCables;
    delete proj.snakes;
    await j('PUT', '/api/project', proj);
    const l = await j('POST', '/api/layer/add', {name: 'Screen1', columns: 10,
        rows: 5, cabinet_width: 128, cabinet_height: 128, offset_x: 0,
        offset_y: 0});
    await j('PUT', `/api/layer/${l.id}`, {processorType: platform,
                                          bitDepth: 8, frameRate: 60});
    let st = await j('POST', '/api/processors', {deviceId: device});
    const pid = st.resolved[st.resolved.length - 1].id;
    const cid = st.resolved[st.resolved.length - 1].slots[0].card.id;
    if (mode) await j('PUT', `/api/processors/${pid}/cards/${cid}`, {mode});
    for (const body of boxes) {
        await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`, body);
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.currentLayer = app.project.layers[0];
    app.selectedLayerIds = new Set([app.project.layers[0].id]);
    await app.refreshProcessors();
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.3; r.panX = 60; r.panY = 40; r.render();
    await app.refreshPortAssignment();
    app.renderHardwareDock();
    app.resetHistory('Unit Seed');
    return {pid, cid, s1: l.id};
}"""

ARMOR = 'novastar-armor'
COEX = 'novastar-coex-1g'


def test_a_backup_box_on_a_screen_on_the_units_own_ports_says_so(page):
    """The owner's sequence: 4K-Prime, + Box, CVT4K-S on OPT 3-4, Backup. The
    unit's own ports are the primary, so the box's drop has nothing to land
    and its backup already rides on it. A working screen is never sent to
    be cleared."""
    pg, errors = page
    ids = pg.evaluate(UNIT_SEED_JS, ['novastar-4k-prime', None, [], ARMOR])
    pg.wait_for_timeout(500)
    pg.locator(f'[data-lrd-field="dock-addbox-{ids["cid"]}"]').click()
    pg.locator(f'[data-lrd-field="dock-addbox-{ids["cid"]}-novastar-cvt4k-s-opt2"]').click()
    pg.wait_for_selector('#copy-role-modal', state='visible')
    pg.locator('#copy-role-backup').click()
    pg.wait_for_timeout(800)
    box = pg.evaluate(BOXES_JS, ids['cid'])[0]
    assert drag(pg, f"card-{ids['cid']}", ids['s1'])['text'] == '2 ports'
    before = pg.evaluate("() => window.app.history.length")
    pg.evaluate("() => { document.getElementById('status-message').textContent = ''; }")
    pill = drag(pg, box_key(pg, box['id']), ids['s1'])
    want = (f"Screen1 is on 4K-Prime, so its backup already rides on "
            f"{box['title']}.")
    assert pill == {'text': want, 'bad': True}, pill
    assert pg.evaluate(STATUS_JS) == want
    assert pg.evaluate("() => window.app.history.length") == before
    # nothing moved, and undo takes back the card drop as it always did
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(900)
    assert errors == []


def test_the_words_behind_a_primary_box_stay(page):
    pg, errors = page
    ids = seed(pg, 'api-backup')
    boxes = pg.evaluate(BOXES_JS, ids['cid'])
    assert drag(pg, box_key(pg, boxes[0]['id']), ids['s1'])['text'] == '2 ports'
    pill = drag(pg, box_key(pg, boxes[1]['id']), ids['s1'])
    assert pill == {
        'text': 'Screen1 is on CVT4K-S A-B, so its backup already rides on '
                'CVT4K-S C-D.', 'bad': True}, pill
    assert errors == []


def test_a_plain_box_is_no_backup_box(page):
    """MX40 Pro in 40-port mode: the box on OPT 3 delivers ports of its own
    and backs up nothing, so it keeps the words it had."""
    pg, errors = page
    ids = pg.evaluate(UNIT_SEED_JS, [
        'novastar-mx40-pro', '40-port',
        [{'deviceId': CVT10, 'pair': False}] * 3, COEX])
    pg.wait_for_timeout(500)
    box = pg.evaluate(BOXES_JS, ids['cid'])[2]
    assert box['first'] == 21 and box['role'] is None, box
    assert drag(pg, f"card-{ids['cid']}", ids['s1'])['text'] == '2 ports'
    pill = drag(pg, box_key(pg, box['id']), ids['s1'])
    assert pill == {'text': 'Every port of Screen1 is already on a processor. '
                            'Clear it first.', 'bad': True}, pill
    assert errors == []


def test_a_screen_on_ports_the_box_does_not_back_up_keeps_the_words(page):
    """MX40 Pro in 20-port mode: the box on OPT 3 backs up OPT 1's ports 1-10
    and no others. A screen on ports 11-12 is not what it backs up."""
    pg, errors = page
    ids = pg.evaluate(UNIT_SEED_JS, [
        'novastar-mx40-pro', '20-port', [{'deviceId': CVT10}], COEX])
    pg.wait_for_timeout(500)
    boxes = pg.evaluate(BOXES_JS, ids['cid'])
    backup = next(b for b in boxes if b['role'] == 'backup')
    pg.evaluate("""async (ids) => {
        await window.app._assignmentRequest(
            '/api/port-assignments/place-overflow', 'POST',
            {layerId: String(ids.s1), cardId: ids.cid, firstPort: 11,
             lastPort: 12});
        await window.app.refreshPortAssignment();
    }""", ids)
    pg.wait_for_timeout(500)
    ports = pg.evaluate("""(ids) => window.app._assignment.screens
        .find(s => s.layerId === String(ids.s1)).ports.map(p => p.port)""", ids)
    assert ports == [11, 12], ports
    pill = drag(pg, box_key(pg, backup['id']), ids['s1'], release=False)
    assert pill == {'text': 'Every port of Screen1 is already on a processor. '
                            'Clear it first.', 'bad': True}, pill
    assert errors == []
