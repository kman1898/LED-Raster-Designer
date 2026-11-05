"""A breakout box set to Mirror, dropped on a screen, makes it the mirror
(owner, 2026-11-04: "breakout is the only way mirror works aka copy").

The owner's beta.5 sequence: a NovaPro UHD Jr, a CVT4K-S A-B on OPT 1-2 and
a second CVT4K-S C-D on OPT 3-4 picked as Mirror (the catalog's per-box copy
OPTs: "OPT 3 serves as the copy/hot backup for OPT 1"). Box A-B onto Screen1
fed it; box C-D onto Screen2 lit "2 ports" and then did nothing, and the
tray said to set the mirror "in Screen Info", which has no such setting.

Now, in one step and one undo entry, the drop sets Screen2 to mirror the
screen on the sockets the box copies, and its run lands on the box's
sockets. A drop that cannot work says why on the drag pill BEFORE the
release (sizes differ, nothing on the copied sockets yet, a locked screen)
and changes nothing; the pill never says ok for a drop the app refuses.
A box set to Backup still drops as its primary: the screen goes on the
sockets it backs up, and its backup rides on the box.

Run locally:
    python -m pytest tests/test_mirror_box_drop.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Screen1 and Screen2 the same 10 x 5 wall of 128 px cabinets (two ports
# each on the UHD Jr), WIDE one column wider, and the UHD Jr with box A-B.
# `mirrorRole` adds the second CVT4K-S as the owner did: through the tray's
# + Box and the Mirror / Backup question, or straight through the route.
SEED_JS = """async (role) => {
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
    const add = (name, columns, x, y) => j('POST', '/api/layer/add', {name,
        columns, rows: 5, cabinet_width: 128, cabinet_height: 128,
        offset_x: x, offset_y: y || 0});
    const made = {};
    for (const [n, c, x, y] of [['Screen1', 10, 0], ['Screen2', 10, 1500],
                                ['WIDE', 11, 0, 900]]) {
        const l = await add(n, c, x, y);
        await j('PUT', `/api/layer/${l.id}`, {processorType: 'novastar-armor',
                                              bitDepth: 8, frameRate: 60});
        made[n] = l.id;
    }
    let st = await j('POST', '/api/processors',
                     {deviceId: 'novastar-novapro-uhd-jr'});
    const pid = st.resolved[st.resolved.length - 1].id;
    const cid = st.resolved[st.resolved.length - 1].slots[0].card.id;
    await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`,
            {deviceId: 'novastar-cvt4k-s'});
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.currentLayer = app.project.layers[0];
    app.selectedLayerIds = new Set([app.project.layers[0].id]);
    await app.refreshProcessors();
    app.renderLayers();
    if (role === 'api-mirror' || role === 'api-backup') {
        await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`,
                {deviceId: 'novastar-cvt4k-s',
                 copyRole: role === 'api-mirror' ? 'mirror' : 'backup'});
        await app.refreshProcessors();
    }
    const r = window.canvasRenderer;
    r.zoom = 0.3; r.panX = 60; r.panY = 40; r.render();
    await app.refreshPortAssignment();
    app.renderHardwareDock();
    app.resetHistory('Mirror Box Seed');
    return {pid, cid, s1: made.Screen1, s2: made.Screen2, wide: made.WIDE};
}"""

BOXES_JS = """(cid) => window.app._dockFindCard(cid).card.cvts.map(b => ({
    id: b.id, title: b.displayTitle, role: b.copyRole || null,
    first: b.firstPort, count: b.portCount}))"""

# A cabinet on the screen's LAST port in client coordinates (the canvas
# gestures' walk): a whole-box drop takes the unplaced ports up to it.
POINT_JS = """(layerId) => {
    const app = window.app;
    const r = window.canvasRenderer;
    const layer = app.project.layers.find(l => l.id === layerId);
    const items = app.calculatePortAssignments(layer)
        .filter(i => i && i.panel && !i.panel.hidden);
    const top = Math.max(...items.map(i => i.port));
    const p = items.filter(i => i.port === top).pop().panel;
    const {dx, dy} = r.getLayerRenderOffset(layer);
    const off = r._layerCanvasOffset(layer);
    const wx = p.x + p.width / 2 + dx + off.wx;
    const wy = p.y + p.height / 2 + dy + off.wy;
    const rect = r.canvas.getBoundingClientRect();
    return {x: rect.left + wx * r.zoom + r.panX,
            y: rect.top + wy * r.zoom + r.panY};
}"""

PILL_JS = """() => {
    const el = document.getElementById('hw-dock-pill');
    if (!el || el.style.display === 'none') return null;
    return {text: el.textContent, bad: el.classList.contains('hw-dock-pill-bad')};
}"""

STATE_JS = """async (ids) => {
    const app = window.app;
    const layer = (id) => app.project.layers.find(l => l.id === id);
    const scr = (id) => app._assignment.screens
        .find(s => s.layerId === String(id));
    const server = await (await fetch('/api/project')).json();
    const slayer = (id) => server.layers.find(l => l.id === id);
    const mo = (l) => (l && l.dataMirrorOf !== undefined
        && l.dataMirrorOf !== null) ? l.dataMirrorOf : null;
    const flag = document.getElementById('hw-dock-flag');
    const n = flag ? flag.querySelector('.hw-dock-flag-n') : null;
    return {
        mirrorOf: mo(layer(ids.s2)), serverMirrorOf: mo(slayer(ids.s2)),
        s1: scr(ids.s1).ports.map(p => [p.port, p.source]),
        s2: scr(ids.s2).ports.map(p => [p.port, p.source]),
        s2unplaced: scr(ids.s2).unplaced,
        pins: ((app.project.port_assignments || {}).pins || [])
            .map(p => [p.layerId, p.index, p.port]).sort(),
        serverPins: ((server.port_assignments || {}).pins || [])
            .map(p => [p.layerId, p.index, p.port]).sort(),
        flagOk: flag ? flag.classList.contains('hw-dock-flag-ok') : null,
        flagN: n ? Number(n.textContent) : null,
        history: app.history.length,
        last: app.history.length ? app.history[app.history.length - 1].action
            : null,
    };
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

STATUS_JS = "() => document.getElementById('status-message').textContent"

# The preview and the release for a box drop through the same two calls
# the drag makes (preview == result), on the handle's own payload.
DROP_JS = """async ([cid, boxId, layerId]) => {
    const app = window.app;
    const box = app._dockFindCard(cid).card.cvts.find(b => b.id === boxId);
    const nums = box.portNumbers || [];
    const payload = {type: 'box', cardId: cid, boxId,
        first: Math.min(...nums), last: Math.max(...nums),
        title: box.displayTitle, beyondTrunks: !!box.beyondTrunks};
    const target = app._dockDataScreenTarget({payload}, String(layerId), null);
    const before = app.history.length;
    const status = document.getElementById('status-message');
    if (status) status.textContent = '';
    await app._dockPerformDrop(payload, target);
    await new Promise(r => setTimeout(r, 400));
    await app.refreshPortAssignment();
    return {pill: target.pill || null, lit: (target.nums || []).length,
            changed: app.history.length !== before,
            said: status ? status.textContent : ''};
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    # No real save or open dialog may pop on the desktop.
    for ep in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{ep}',
                 lambda route: route.fulfill(status=403, body=''))
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


def seed(pg, role):
    ids = pg.evaluate(SEED_JS, role)
    pg.wait_for_timeout(500)
    return ids


def box_key(pg, box_id):
    """The tray handle a person grabs for this box."""
    for key in (f'box-{box_id}', f'loop-{box_id}'):
        if pg.locator(f'[data-hwdock="{key}"]').count():
            return key
    keys = pg.evaluate("""() => [...document.querySelectorAll('[data-hwdock]')]
        .map(e => e.dataset.hwdock)""")
    raise AssertionError(f'no tray handle for {box_id}: {keys}')


def grip(pg, key):
    """Where a hand takes a tray handle: a header's grip, a chip's face."""
    pg.evaluate("""(key) => {
        const el = document.querySelector(`[data-hwdock="${key}"]`);
        if (el) el.scrollIntoView({block: 'nearest'});
    }""", key)
    head = pg.locator(f'[data-hwdock="{key}"]')
    handle = head.locator('.hw-dock-grip')
    loc = handle.first if handle.count() else head.first
    box = loc.bounding_box()
    assert box, f'no grip on {key}'
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def drag(pg, key, layer_id, release=True):
    """A real pointer drag from a tray handle onto a screen: the pill as the
    person sees it just before the release, then the release."""
    sx, sy = grip(pg, key)
    end = pg.evaluate(POINT_JS, layer_id)
    pg.mouse.move(sx, sy)
    pg.mouse.down()
    pg.mouse.move((sx + end['x']) / 2, (sy + end['y']) / 2, steps=5)
    pg.mouse.move(end['x'], end['y'], steps=5)
    pg.wait_for_timeout(250)
    pill = pg.evaluate(PILL_JS)
    if not release:
        pg.mouse.move(30, 300, steps=3)
    pg.mouse.up()
    pg.wait_for_timeout(900)
    return pill


def add_mirror_box_like_the_owner(pg, ids):
    """+ Box on the UHD Jr, then Mirror in the copy-role question."""
    pg.evaluate("(ids) => window.app._dockAddBox(ids.cid, 'novastar-cvt4k-s')",
                ids)
    pg.wait_for_selector('#copy-role-modal', state='visible')
    pg.locator('#copy-role-mirror').click()
    pg.wait_for_timeout(800)
    boxes = pg.evaluate(BOXES_JS, ids['cid'])
    assert [(b['title'], b['role'], b['first']) for b in boxes] == [
        ('CVT4K-S A-B', None, 1), ('CVT4K-S C-D', 'mirror', 17)], boxes
    return boxes


def test_the_owners_sequence_makes_screen2_the_mirror_in_one_step(page):
    pg, errors = page
    ids = seed(pg, None)
    boxes = add_mirror_box_like_the_owner(pg, ids)
    primary, mirror = boxes[0]['id'], boxes[1]['id']
    pill = drag(pg, box_key(pg, primary), ids['s1'])
    assert pill and not pill['bad'] and pill['text'] == '2 ports', pill
    st = pg.evaluate(STATE_JS, ids)
    assert st['s1'] == [[1, 'pin'], [2, 'pin']], st
    assert st['flagN'] == 2 and st['flagOk'] is False, st
    before = st['history']

    pill = drag(pg, box_key(pg, mirror), ids['s2'])
    assert pill == {'text': 'Copy of Screen1', 'bad': False}, pill
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] == ids['s1'] and st['serverMirrorOf'] == ids['s1']
    # Screen1 on A-B 1-2, so Screen2's run is on C-D's copies of them
    assert st['s2'] == [[17, 'mirror'], [18, 'mirror']], st
    assert st['s2unplaced'] == []
    # Screen2 attached (WIDE is the one screen left): the flag counts it off
    assert st['flagN'] == 1, st
    assert st['history'] == before + 1 and st['last'] == 'Mirror Screen', st
    assert not [t for t in pg.evaluate(TOASTS_JS) if t['err']]

    # ONE undo restores everything, server included
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(900)
    pg.evaluate("() => window.app.refreshPortAssignment()")
    pg.wait_for_timeout(300)
    back = pg.evaluate(STATE_JS, ids)
    assert back['mirrorOf'] is None and back['serverMirrorOf'] is None, back
    assert back['s2'] == [[None, None], [None, None]], back
    assert back['s2unplaced'] == [0, 1]
    assert back['s1'] == [[1, 'pin'], [2, 'pin']]
    assert back['pins'] == back['serverPins'], back
    assert back['flagN'] == 2, back
    # and redo puts the mirror back
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(900)
    pg.evaluate("() => window.app.refreshPortAssignment()")
    pg.wait_for_timeout(300)
    again = pg.evaluate(STATE_JS, ids)
    assert again['mirrorOf'] == ids['s1'] and again['serverMirrorOf'] == ids['s1']
    assert again['s2'] == [[17, 'mirror'], [18, 'mirror']], again
    assert errors == []


def _refusal_rig(pg, case):
    ids = seed(pg, 'api-mirror')
    boxes = pg.evaluate(BOXES_JS, ids['cid'])
    primary, mirror = boxes[0]['id'], boxes[1]['id']
    target = ids['s2']
    if case != 'empty-primary':
        out = pg.evaluate(DROP_JS, [ids['cid'], primary, ids['s1']])
        assert out['changed'] and out['pill']['ok'], out
    if case == 'size':
        target = ids['wide']
    if case == 'locked':
        pg.evaluate("""(id) => {
            const app = window.app;
            const l = app.project.layers.find(x => x.id === id);
            l.locked = true;
            app.updateLayers([l]);
        }""", target)
        pg.wait_for_timeout(300)
    return ids, mirror, target


REFUSALS = {
    'size': ('WIDE is 11 x 5 cabinets and Screen1 is 10 x 5. A mirror screen '
             'must match the screen it copies.'),
    'empty-primary': ('Put a screen on CVT4K-S A-B first. Then drag '
                      'CVT4K-S C-D onto the screen that should copy it.'),
    'locked': 'Screen2 is locked. Unlock it to change it.',
}


@pytest.mark.parametrize('case', sorted(REFUSALS))
def test_a_drop_that_cannot_mirror_says_why_before_the_drop(page, case):
    pg, errors = page
    ids, mirror, target = _refusal_rig(pg, case)
    pg.evaluate(TOASTS_JS)
    before = pg.evaluate(STATE_JS, ids)
    want = REFUSALS[case]
    # the real drag: the pill says it while the box is still in hand
    pill = drag(pg, box_key(pg, mirror), target)
    assert pill == {'text': want, 'bad': True}, pill
    after = pg.evaluate(STATE_JS, ids)
    toasts = pg.evaluate(TOASTS_JS)
    # nothing changed: no mirror, no ports, no history step
    assert after['history'] == before['history'], (before, after)
    assert after['pins'] == before['pins']
    assert after['serverPins'] == before['serverPins']
    layer_mirror = pg.evaluate("""(id) => {
        const l = window.app.project.layers.find(x => x.id === id);
        return l.dataMirrorOf === undefined ? null : l.dataMirrorOf;
    }""", target)
    assert layer_mirror is None
    if case == 'locked':
        # the locked-screens rule: the release shows the locked error
        assert any(t['err'] and t['msg'] == want for t in toasts), toasts
    else:
        assert pg.evaluate(STATUS_JS) == want
    assert errors == []


def test_a_mismatch_matches_the_servers_own_words(page):
    """The pill's mismatch is the server's mirror_set_refusal, word for
    word: the two cannot drift apart unseen."""
    pg, errors = page
    ids, mirror, target = _refusal_rig(pg, 'size')
    out = pg.evaluate(DROP_JS, [ids['cid'], mirror, target])
    server = pg.evaluate("""async ([id, of]) => (await (await fetch(
        `/api/layer/${id}/mirror-refusal?of=${of}`)).json()).error""",
                         [target, ids['s1']])
    assert out['pill'] == {'ok': False, 'message': server}, (out, server)
    assert not out['changed']
    assert errors == []


def test_the_pill_never_says_ok_for_a_drop_the_app_refuses(page):
    """Every box drop on every screen of the rig: the pill says ok exactly
    when the release changes something, and a refusal is said."""
    pg, errors = page
    ids = seed(pg, 'api-mirror')
    boxes = pg.evaluate(BOXES_JS, ids['cid'])
    primary, mirror = boxes[0]['id'], boxes[1]['id']
    pg.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        l.locked = true;
        app.updateLayers([l]);
    }""", ids['wide'])
    pg.wait_for_timeout(300)
    steps = [
        (mirror, ids['s2']),    # nothing on A-B yet
        (primary, ids['wide']),  # locked
        (primary, ids['s1']),    # lands
        (primary, ids['s1']),    # already all placed
        (mirror, ids['s1']),     # the source itself
        (mirror, ids['wide']),   # locked
        (mirror, ids['s2']),     # the mirror
        (mirror, ids['s2']),     # already mirrors
        (primary, ids['s2']),    # a mirror takes no ports of its own
    ]
    seen = []
    for box, layer in steps:
        out = pg.evaluate(DROP_JS, [ids['cid'], box, layer])
        seen.append((box, layer, out))
        pill = out['pill'] or {}
        assert bool(pill.get('ok')) == out['changed'], seen
        if not pill.get('ok'):
            assert pill.get('message'), seen
    assert [s[2]['changed'] for s in seen] == [
        False, False, True, False, False, False, True, False, False], seen
    assert errors == []


def test_a_server_refusal_after_an_ok_pill_is_said_where_the_drop_was(page):
    """The general net: should the server still refuse a fill the pill
    could not foresee, the refusal is said in the status bar, not only on
    the tray's line (the drop must never look like it did nothing)."""
    pg, errors = page
    ids = seed(pg, 'api-mirror')
    boxes = pg.evaluate(BOXES_JS, ids['cid'])
    said = pg.evaluate("""async ([cid, box, layerId]) => {
        const app = window.app;
        document.getElementById('status-message').textContent = '';
        await app._takeOffer({action: 'place-overflow', layerId: String(layerId),
            cardId: cid, firstPort: 17, lastPort: 32, boxId: box,
            fromDock: true});
        return document.getElementById('status-message').textContent;
    }""", [ids['cid'], boxes[1]['id'], ids['s2']])
    assert said == ('CVT4K-S C-D copies CVT4K-S A-B for a mirror screen. Put '
                    'a screen on CVT4K-S A-B first, then drag CVT4K-S C-D '
                    'onto the screen that should copy it.'), said
    assert errors == []


def test_a_backup_box_drops_as_its_primary(page):
    """A CVT4K-S on OPT 3-4 set to Backup backs up A-B: dragging it onto a
    screen lands the screen on the sockets it backs up, its backup riding
    on the box; on a screen already there it says so and changes nothing."""
    pg, errors = page
    ids = seed(pg, 'api-backup')
    boxes = pg.evaluate(BOXES_JS, ids['cid'])
    assert [(b['title'], b['role']) for b in boxes] == [
        ('CVT4K-S A-B', None), ('CVT4K-S C-D', 'backup')], boxes
    backup = boxes[1]['id']
    out = pg.evaluate(DROP_JS, [ids['cid'], backup, ids['s1']])
    assert out['pill'] == {'ok': True, 'text': '2 ports'}, out
    assert out['changed']
    st = pg.evaluate(STATE_JS, ids)
    assert st['s1'] == [[1, 'pin'], [2, 'pin']], st
    backed = pg.evaluate("""(cid) => {
        const app = window.app;
        return [1, 2].map(n => app._portOccupants(cid, n).map(o => o.name));
    }""", ids['cid'])
    assert backed == [['Screen1'], ['Screen1']], backed
    again = pg.evaluate(DROP_JS, [ids['cid'], backup, ids['s1']])
    assert again['pill'] == {
        'ok': False, 'message': 'Screen1 is on CVT4K-S A-B, so its backup '
                                'already rides on CVT4K-S C-D.'}, again
    assert not again['changed']
    assert errors == []


# Any payload through the drag's two calls, preview then release.
PAYLOAD_DROP_JS = """async ([payload, target]) => {
    const app = window.app;
    const t = target || app._dockDataScreenTarget({payload},
                                                  String(payload.onto), null);
    const before = app.history.length;
    const status = document.getElementById('status-message');
    if (status) status.textContent = '';
    await app._dockPerformDrop(payload, t);
    await new Promise(r => setTimeout(r, 400));
    await app.refreshPortAssignment();
    return {pill: t.pill || null, changed: app.history.length !== before,
            said: status ? status.textContent : ''};
}"""

ADD_SCREEN_JS = """async ([name, x, y, extra]) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)}).then(r => r.json());
    const l = await j('POST', '/api/layer/add', Object.assign({name,
        columns: 10, rows: 5, cabinet_width: 128, cabinet_height: 128,
        offset_x: x, offset_y: y}, extra || {}));
    await j('PUT', `/api/layer/${l.id}`, {processorType: 'novastar-armor',
                                          bitDepth: 8, frameRate: 60});
    const app = window.app;
    app.project = await (await fetch('/api/project')).json();
    await app.refreshProcessors();
    app.renderLayers();
    await app.refreshPortAssignment();
    return l.id;
}"""

RELOAD_JS = """async () => {
    const app = window.app;
    app.project = await (await fetch('/api/project')).json();
    await app.refreshProcessors();
    app.renderLayers();
    await app.refreshPortAssignment();
}"""

SERVER_REFUSAL_JS = """async ([id, of]) => (await (await fetch(
    `/api/layer/${id}/mirror-refusal?of=${of}`)).json()).error"""


def mirror_rig(pg):
    """The owner's rig with Screen1 already on box A-B."""
    ids = seed(pg, 'api-mirror')
    boxes = pg.evaluate(BOXES_JS, ids['cid'])
    primary, mirror = boxes[0]['id'], boxes[1]['id']
    out = pg.evaluate(DROP_JS, [ids['cid'], primary, ids['s1']])
    assert out['changed'], out
    return ids, primary, mirror


def test_unplugging_the_copy_or_its_source_follows_the_box_drop(page):
    pg, errors = page
    ids, primary, mirror = mirror_rig(pg)
    assert pg.evaluate(DROP_JS, [ids['cid'], mirror, ids['s2']])['changed']
    st = pg.evaluate(STATE_JS, ids)
    assert st['s2'] == [[17, 'mirror'], [18, 'mirror']], st

    # the copy's chip dragged back to the tray: only the copy goes
    out = pg.evaluate(PAYLOAD_DROP_JS, [
        {'type': 'port', 'cardId': ids['cid'], 'port': 17, 'title': 'P'},
        {'kind': 'dock'}])
    assert out['changed'], out
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None and st['serverMirrorOf'] is None, st
    assert st['s2'] == [[None, None], [None, None]], st
    assert st['s1'] == [[1, 'pin'], [2, 'pin']], st

    # made again, then the SOURCE comes off its box: the copy goes with it
    assert pg.evaluate(DROP_JS, [ids['cid'], mirror, ids['s2']])['changed']
    assert pg.evaluate(STATE_JS, ids)['mirrorOf'] == ids['s1']
    pg.evaluate("""async (ids) => {
        await window.app._dockReleasePins(
            [0, 1].map(index => ({layerId: String(ids.s1), index})),
            'Release Ports');
    }""", ids)
    pg.wait_for_timeout(400)
    st = pg.evaluate(STATE_JS, ids)
    assert st['mirrorOf'] is None and st['serverMirrorOf'] is None, st
    assert st['s1'] == [[None, None], [None, None]], st
    assert st['s2'] == [[None, None], [None, None]], st
    assert errors == []


def test_the_processor_drag_and_the_box_drop_land_the_same(page):
    """The UHD Jr's catalog mode is copyTrunks per-box: with a box set to
    Mirror the processor drag already made a mirror. Both gestures end in
    the same setting on the same sockets."""
    pg, errors = page
    ids, primary, mirror = mirror_rig(pg)
    payload = {'type': 'processor', 'processorId': ids['pid'],
               'onto': ids['s2']}
    out = pg.evaluate(PAYLOAD_DROP_JS, [payload, None])
    assert out['pill'] == {'ok': True, 'text': 'Copy of Screen1'}, out
    by_processor = pg.evaluate(STATE_JS, ids)
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(900)
    pg.evaluate("() => window.app.refreshPortAssignment()")
    pg.wait_for_timeout(300)
    assert pg.evaluate(STATE_JS, ids)['mirrorOf'] is None
    out = pg.evaluate(DROP_JS, [ids['cid'], mirror, ids['s2']])
    assert out['pill'] == {'ok': True, 'text': 'Copy of Screen1'}, out
    by_box = pg.evaluate(STATE_JS, ids)
    assert by_box['mirrorOf'] == by_processor['mirrorOf'] == ids['s1']
    assert by_box['s2'] == by_processor['s2'] == [[17, 'mirror'],
                                                  [18, 'mirror']]
    assert errors == []


def test_a_backup_box_dragged_from_the_tray_by_a_person(page):
    """The same backup drop as a real pointer drag from the box's own tray
    handle, so the payload is the one the tray builds."""
    pg, errors = page
    ids = seed(pg, 'api-backup')
    backup = pg.evaluate(BOXES_JS, ids['cid'])[1]['id']
    pill = drag(pg, box_key(pg, backup), ids['s1'])
    assert pill == {'text': '2 ports', 'bad': False}, pill
    st = pg.evaluate(STATE_JS, ids)
    assert st['s1'] == [[1, 'pin'], [2, 'pin']], st
    pill = drag(pg, box_key(pg, backup), ids['s1'])
    assert pill == {'text': 'Screen1 is on CVT4K-S A-B, so its backup already '
                            'rides on CVT4K-S C-D.', 'bad': True}, pill
    assert pg.evaluate(STATE_JS, ids)['history'] == st['history']
    assert errors == []


def _parity_target(pg, ids, mirror, case):
    """Sets up one of the server's rules; returns (target id, source id)."""
    if case == 'pixels':
        return pg.evaluate(ADD_SCREEN_JS, [
            'ODD', 1500, 900, {'cabinet_height': 64}]), ids['s1']
    if case == 'blank':
        target = pg.evaluate(ADD_SCREEN_JS, ['HOLE', 1500, 900, None])
        pg.evaluate("""async (id) => {
            const app = window.app;
            const l = app.project.layers.find(x => x.id === id);
            app.selectLayer(l);
            await app.setPanelsBlankBulk(
                [l.panels.find(x => x.row === 0 && x.col === 3)], true);
        }""", target)
        pg.wait_for_timeout(400)
        pg.evaluate("() => window.app.refreshPortAssignment()")
        return target, ids['s1']
    if case == 'second-mirror':
        assert pg.evaluate(DROP_JS, [ids['cid'], mirror, ids['s2']])['changed']
        return pg.evaluate(ADD_SCREEN_JS, ['S3', 1500, 900, None]), ids['s1']
    if case == 'group':
        third = pg.evaluate(ADD_SCREEN_JS, ['S3', 1500, 900, None])
        pg.evaluate("""async ([a, b]) => {
            const proj = await (await fetch('/api/project')).json();
            proj.groups = [{id: 'g1', name: 'PAIR', layer_ids: [a, b]}];
            proj.layers.filter(l => l.id === a || l.id === b)
                .forEach(l => { l.group_id = 'g1'; });
            await fetch('/api/project', {method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(proj)});
        }""", [ids['s2'], third])
        pg.evaluate(RELOAD_JS)
        return ids['s2'], ids['s1']
    raise AssertionError(case)


@pytest.mark.parametrize('case,needle', [
    ('pixels', "cabinets are 128 x 64 px"),
    ('blank', 'different blank, hidden or half cabinets'),
    ('second-mirror', 'Screen2 already mirrors Screen1.'),
    ('group', 'routes its data as one screen with the group PAIR'),
])
def test_every_rule_of_the_server_reaches_the_pill_in_its_words(page, case,
                                                                needle):
    pg, errors = page
    ids, primary, mirror = mirror_rig(pg)
    target, source = _parity_target(pg, ids, mirror, case)
    server = pg.evaluate(SERVER_REFUSAL_JS, [target, source])
    assert server and needle in server, server
    out = pg.evaluate(DROP_JS, [ids['cid'], mirror, target])
    assert out['pill'] == {'ok': False, 'message': server}, (out, server)
    assert not out['changed']
    assert errors == []


def test_a_screen_copied_by_another_cannot_become_a_mirror(page):
    """A show saved with a mirror whose source sits unplugged: the source
    cannot itself become a copy (mirror_set_refusal's chain rule)."""
    pg, errors = page
    ids = seed(pg, 'api-mirror')
    boxes = pg.evaluate(BOXES_JS, ids['cid'])
    third = pg.evaluate(ADD_SCREEN_JS, ['S3', 1500, 900, None])
    assert pg.evaluate(DROP_JS, [ids['cid'], boxes[0]['id'], third])['changed']
    pg.evaluate("""async (ids) => {
        await fetch(`/api/layer/${ids.s2}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({dataMirrorOf: ids.s1})});
    }""", ids)
    pg.evaluate(RELOAD_JS)
    server = pg.evaluate(SERVER_REFUSAL_JS, [ids['s1'], third])
    assert server == ('Screen2 mirrors Screen1, so Screen1 cannot mirror '
                      'another screen.'), server
    out = pg.evaluate(DROP_JS, [ids['cid'], boxes[1]['id'], ids['s1']])
    assert out['pill'] == {'ok': False, 'message': server}, out
    assert not out['changed']
    assert errors == []


def test_one_port_of_a_mirror_box_says_to_drag_the_box(page):
    """A single socket of a mirror box dragged onto a screen's run: the
    pill says why before the drop, and the server's refusal is said in the
    status bar as well as on the tray's line."""
    pg, errors = page
    ids, primary, mirror = mirror_rig(pg)
    before = pg.evaluate(STATE_JS, ids)
    pill = drag(pg, f"port-{ids['cid']}-17", ids['s2'])
    assert pill == {'text': 'Port 1 of CVT4K-S C-D carries a copy. Drag '
                            'CVT4K-S C-D onto the screen that should be the '
                            'mirror.', 'bad': True}, pill
    after = pg.evaluate(STATE_JS, ids)
    assert after['history'] == before['history']
    assert after['pins'] == before['pins']
    said = pg.evaluate(STATUS_JS)
    assert 'copies CVT4K-S A-B for a mirror screen.' in said, said
    assert 'Screen Info' not in said
    assert errors == []


# Every shape the catalog gives a copy box: a whole mode (H_4xfiber Copy, the
# VX Pros), a per-box pick (MCTRL R5, 4K-Prime, MX40 Pro 20-port) and a unit
# whose copy OPT only copies (MX30). Only the catalog's own settings are used.
UNIT_SEED_JS = """async ([spec]) => {
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
    const made = {};
    for (const [n, x] of [['SA', 0], ['SB', 900]]) {
        const l = await j('POST', '/api/layer/add', {name: n, columns: 4,
            rows: 2, cabinet_width: 128, cabinet_height: 128, offset_x: x,
            offset_y: 0});
        await j('PUT', `/api/layer/${l.id}`, {processorType: spec.platform,
                                              bitDepth: 8, frameRate: 60});
        made[n] = l.id;
    }
    let st = await j('POST', '/api/processors', {deviceId: spec.device});
    const pid = st.resolved[st.resolved.length - 1].id;
    if (spec.card) {
        st = await j('PUT', `/api/processors/${pid}/slots/0`,
                     {deviceId: spec.card});
    }
    const cid = st.resolved[st.resolved.length - 1].slots[0].card.id;
    if (spec.mode) {
        await j('PUT', `/api/processors/${pid}/cards/${cid}`,
                {mode: spec.mode});
    }
    for (const body of spec.boxes) {
        await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`, body);
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    await app.refreshProcessors();
    app.renderLayers();
    await app.refreshPortAssignment();
    app.resetHistory('Unit Seed');
    const card = app._dockFindCard(cid).card;
    const of = (b) => card.ports.filter(p => p.cvtId === b.id);
    const copy = card.cvts.find(b => of(b).length
        && of(b).every(p => p.mirrorOf));
    const first = copy ? of(copy)[0].mirrorOf : null;
    const primary = copy
        ? card.cvts.find(b => of(b).some(p => p.number === first))
        : card.cvts[0];
    return {cid, sa: made.SA, sb: made.SB,
            copy: copy ? copy.id : null, primary: primary.id,
            other: card.cvts.filter(b => b !== primary).map(b => b.id),
            firstCopy: copy ? of(copy)[0].number : null};
}"""

CVT10 = {'deviceId': 'novastar-cvt10', 'pair': False}
CVT10_MIRROR = dict(CVT10, copyRole='mirror')
CVT4K = {'deviceId': 'novastar-cvt4k-s', 'pair': False}
ARMOR, COEX = 'novastar-armor', 'novastar-coex-1g'
COPY_UNITS = {
    'h-4xfiber-copy': dict(device='novastar-h9', mode='copy', platform=ARMOR,
                           card='novastar-card-h-4xfiber',
                           boxes=[CVT10] * 4),
    'vx1000-pro-copy': dict(device='novastar-vx1000-pro', mode='copy',
                            platform=ARMOR, boxes=[CVT10] * 2),
    'vx2000-pro-copy': dict(device='novastar-vx2000-pro', mode='copy',
                            platform=ARMOR, boxes=[CVT4K] * 2),
    'mctrl-r5-box': dict(device='novastar-mctrl-r5', platform=ARMOR,
                         boxes=[CVT10, CVT10_MIRROR]),
    '4k-prime-box': dict(device='novastar-4k-prime', platform=ARMOR,
                         boxes=[CVT4K, dict(CVT4K, copyRole='mirror')]),
    # its first box brings its OPT 3 pair, which the add sets to Mirror
    'mx40-pro-box': dict(device='novastar-mx40-pro', mode='20-port',
                         platform=COEX, boxes=[{'deviceId': 'novastar-cvt10',
                                                'copyRole': 'mirror'}]),
    'mx30-copy-opt': dict(device='novastar-mx30', platform=COEX,
                          boxes=[CVT10] * 2),
}


@pytest.mark.parametrize('name', sorted(COPY_UNITS))
def test_every_catalog_copy_box_makes_the_mirror_the_same_way(page, name):
    pg, errors = page
    rig = pg.evaluate(UNIT_SEED_JS, [COPY_UNITS[name]])
    assert rig['copy'], (name, rig)
    first = pg.evaluate(DROP_JS, [rig['cid'], rig['primary'], rig['sa']])
    assert first['changed'], (name, first)
    out = pg.evaluate(DROP_JS, [rig['cid'], rig['copy'], rig['sb']])
    assert out['pill'] == {'ok': True, 'text': 'Copy of SA'}, (name, out)
    assert out['changed'], (name, out)
    got = pg.evaluate("""(rig) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === rig.sb);
        const s = app._assignment.screens
            .find(x => x.layerId === String(rig.sb));
        return {mirrorOf: l.dataMirrorOf, ports: s.ports.map(p =>
            [p.port, p.source])};
    }""", rig)
    assert got['mirrorOf'] == rig['sa'], (name, got)
    assert got['ports'] == [[rig['firstCopy'], 'mirror']], (name, got)
    assert errors == []


def test_a_box_on_an_independent_card_stays_an_ordinary_box(page):
    """No copy in the mode, no mirror: the catalog's Independent H_4xfiber
    box drops as any box, and nothing is widened to it."""
    pg, errors = page
    rig = pg.evaluate(UNIT_SEED_JS, [dict(
        COPY_UNITS['h-4xfiber-copy'], mode='independent')])
    assert rig['copy'] is None, rig
    assert pg.evaluate(DROP_JS,
                       [rig['cid'], rig['primary'], rig['sa']])['changed']
    out = pg.evaluate(DROP_JS, [rig['cid'], rig['other'][0], rig['sb']])
    assert out['pill'] == {'ok': True, 'text': '1 port'}, out
    assert out['changed']
    got = pg.evaluate("""(rig) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === rig.sb);
        const s = app._assignment.screens
            .find(x => x.layerId === String(rig.sb));
        return [l.dataMirrorOf === undefined ? null : l.dataMirrorOf,
                s.ports.map(p => p.source)];
    }""", rig)
    assert got == [None, ['pin']], got
    assert errors == []


BACKUP_UNITS = {
    'h-4xfiber-backup': dict(COPY_UNITS['h-4xfiber-copy'], mode='backup'),
    'vx1000-pro-backup': dict(COPY_UNITS['vx1000-pro-copy'], mode='backup'),
    'mctrl-r5-backup': dict(COPY_UNITS['mctrl-r5-box'], boxes=[
        CVT10, dict(CVT10, copyRole='backup')]),
}


@pytest.mark.parametrize('name', sorted(BACKUP_UNITS))
def test_every_catalog_backup_box_drops_or_says_why(page, name):
    pg, errors = page
    rig = pg.evaluate(UNIT_SEED_JS, [BACKUP_UNITS[name]])
    assert rig['copy'] is None, (name, rig)
    backups = pg.evaluate("""(cid) => window.app._dockFindCard(cid).card.cvts
        .filter(b => b.backupOf).map(b => b.id)""", rig['cid'])
    assert backups, (name, rig)
    out = pg.evaluate(DROP_JS, [rig['cid'], backups[0], rig['sa']])
    assert out['pill'] == {'ok': True, 'text': '1 port'}, (name, out)
    assert out['changed'], (name, out)
    again = pg.evaluate(DROP_JS, [rig['cid'], backups[0], rig['sa']])
    assert not again['pill']['ok'] and not again['changed'], (name, again)
    assert 'already rides on' in again['pill']['message'], (name, again)
    assert errors == []
