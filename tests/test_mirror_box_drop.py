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
    pg.evaluate("""(key) => {
        const el = document.querySelector(`[data-hwdock="${key}"]`);
        if (el) el.scrollIntoView({block: 'nearest'});
    }""", key)
    loc = pg.locator(f'[data-hwdock="{key}"] .hw-dock-grip').first
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
