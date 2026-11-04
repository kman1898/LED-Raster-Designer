"""Deleting a typed port cable length throws nothing, and an error the
browser hides from the page is logged as not the app's.

The owner's Mac log, 2026-11-04, 1.6.0-beta.5: clearing typed lengths in
the box cable sheets of Brompton XD boxes in redundancy loops, every
Backspace logged

    client_error {"message": "Script error.", "filename": "", "lineno": 0,
                  "colno": 0, "stack": "", "lastInput": {"key": "Backspace",
                  "field": "data-cable-ft-..."}}

and the cleared length still saved. A browser gives a page that bare form
only for a throw in a script from another origin: every script of the app
is the page's own origin, so a throw in it carries its file and line.
Typing then deleting in every one of these fields (open loop rows, the
far box's backup ports, the folded strip's sheet, a length the stock
writes as two pieces) throws nothing in the app. So:

  * the round trip in each kind of field leaves no page error, no console
    error and no client_error, and the cleared length is gone from the
    store
  * a throw from a foreign-origin script on that same Backspace reaches the
    log in exactly the owner's form, tagged opaque and not actionable
  * a throw from the app's own origin keeps its file and line, untagged

Synthetic hardware only: one SX40 in redundancy (XD A loops to B), one
wall placed on its card.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


FOREIGN = 'http://foreign-script.invalid/throws.js'

SEED_JS = """async () => {
    const app = window.app;
    const send = (url, method, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) })
        .then(r => r.json());
    const proj = await send('/api/project', 'GET');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    proj.beaches = []; proj.snakes = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.fiberCables;
    delete proj.pullSheetEdits;
    await send('/api/project', 'PUT', proj);
    const wall = await send('/api/layer/add', 'POST', { name: 'WALL', columns: 6,
        rows: 4, cabinet_width: 500, cabinet_height: 500 });
    await send(`/api/layer/${wall.id}`, 'PUT', { processorType: 'brompton',
        bitDepth: 8, frameRate: 60 });
    const last = (st) => st.resolved[st.resolved.length - 1];
    const proc = last(await send('/api/processors', 'POST',
                                 { deviceId: 'brompton-sx40' }));
    await send(`/api/processors/${proc.id}`, 'PUT', { redundancy: true });
    app.project = await send('/api/project', 'GET');
    app.dedupeProjectLayers('cable_length_delete');
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    const card = app._processorsResolved.find(p => p.id === proc.id).slots[0].card;
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                 { layerId: String(wall.id), cardId: card.id });
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    const boxes = card.cvts.map(c => c.id);
    return { proc: proc.id, card: card.id, near: boxes[0], far: boxes[1],
             ports: app.getLayerPortsRequired(app.project.layers[0]) };
}"""

# One sheet up, the loop strip folded or open, the dock redrawn.
SHEET_JS = """([box, folded, ids]) => {
    const app = window.app;
    [ids.near, ids.far].forEach(b => {
        app._setDataCableSheetOpen({ kind: 'cvt', id: b }, b === box);
        try {
            localStorage.setItem('ledRasterPanelCollapsed_hwdock-box-' + b,
                                 folded ? '1' : '0');
        } catch (_) { /* no storage */ }
    });
    app.renderHardwareDock();
}"""

FIELDS_JS = """(box) => [...document.querySelectorAll(
        `[data-lrd-cable-sheet="cvt:${box}"] [data-lrd-field^="data-cable-ft-${box}-"]`)]
    .filter(e => e.offsetParent && e.getBoundingClientRect().height > 0)
    .map(e => e.dataset.lrdField)"""

STORED_JS = """([box, key]) => {
    const rec = window.app._processorsResolved.flatMap(p => p.slots)
        .map(s => s.card).filter(Boolean).flatMap(c => c.cvts || [])
        .find(c => c.id === box);
    return ((rec && rec.portCables) || {})[key] || null;
}"""

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


def _quiet(page):
    page.evaluate("() => { window.__lrdQuiet = 0; }")
    page.wait_for_function(QUIET_JS)


def _open(pw_browser, e2e_server):
    context = pw_browser.new_context(viewport={'width': 1800, 'height': 1200})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    page = context.new_page()
    seen = {'page': [], 'console': [], 'logged': []}
    page.on('pageerror', lambda e: seen['page'].append(f'{e}\n{e.stack or ""}'))
    page.on('console', lambda m: seen['console'].append(m.text)
            if m.type == 'error' and '/api/panel-catalog' not in (m.location or {}).get('url', '')
            and 'BAD GATEWAY' not in m.text else None)

    def on_request(req):
        if req.url.endswith('/api/log') and req.method == 'POST':
            try:
                body = json.loads(req.post_data or '{}')
            except ValueError:
                return
            if body.get('action') in ('client_error', 'client_unhandled_rejection'):
                seen['logged'].append(body)
    page.on('request', on_request)
    # The real save/open dialogs would pop up on the desktop.
    for path in ('save-file', 'open-file', 'select-directory'):
        page.route(f'**/api/native-dialog/{path}', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body='{"cancelled": true}'))
    page.goto(e2e_server, wait_until='domcontentloaded')
    page.wait_for_function(
        "() => window.app && window.app._initialLoadComplete === true"
        " && window.app._socketConnects >= 1")
    _quiet(page)
    ids = page.evaluate(SEED_JS)
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_function("() => window.canvasRenderer.viewMode === 'data-flow'")
    _quiet(page)
    return context, page, ids, seen


def _type_then_delete(page, box, key, text):
    """Type a length and commit it, then take it out one Backspace at a
    time and commit the blank: the owner's gesture."""
    field = page.locator(f'[data-lrd-field="data-cable-ft-{box}-{key}"]')
    field.click()
    page.keyboard.press('ControlOrMeta+a')
    page.keyboard.type(text)
    page.keyboard.press('Enter')
    _quiet(page)
    typed = page.evaluate(STORED_JS, [box, key])
    field = page.locator(f'[data-lrd-field="data-cable-ft-{box}-{key}"]')
    field.click()
    page.keyboard.press('End')
    for _ in text:
        page.keyboard.press('Backspace')
    assert field.input_value() == ''
    page.keyboard.press('Enter')
    _quiet(page)
    return typed, page.evaluate(STORED_JS, [box, key])


@pytest.mark.parametrize('box_role, folded', [
    ('near', False),   # the loop's primary, its row open
    ('far', False),    # the loop end: every socket backs up the primary's
    ('near', True),    # the folded strip's sheet, under its header
])
def test_deleting_a_typed_length_throws_nothing(
        e2e_server, pw_browser, box_role, folded):
    context, page, ids, seen = _open(pw_browser, e2e_server)
    try:
        assert ids['ports'] >= 2, ids
        box = ids[box_role]
        page.evaluate(SHEET_JS, [box, folded, ids])
        _quiet(page)
        keys = page.evaluate(FIELDS_JS, box)
        assert len(keys) >= 2, keys
        prefix = f'data-cable-ft-{box}-'
        # a stock length, and one the stock writes in two pieces
        for key, text in ((keys[0][len(prefix):], '25'),
                          (keys[1][len(prefix):], '130')):
            typed, cleared = _type_then_delete(page, box, key, text)
            assert (typed or {}).get('ft') == int(text), (key, typed)
            assert cleared is None, (key, cleared)
        assert seen['page'] == [], seen['page']
        assert seen['console'] == [], seen['console']
        assert seen['logged'] == [], seen['logged']
    finally:
        context.close()


def test_an_error_the_browser_hides_is_logged_as_not_the_apps(
        e2e_server, pw_browser):
    context, page, ids, seen = _open(pw_browser, e2e_server)
    try:
        box = ids['near']
        page.evaluate(SHEET_JS, [box, False, ids])
        _quiet(page)
        key = page.evaluate(FIELDS_JS, box)[0][len(f'data-cable-ft-{box}-'):]
        # A script from another origin listening on the page, the way an
        # extension's content script does, throwing on Backspace.
        page.route(FOREIGN, lambda route: route.fulfill(
            status=200, content_type='text/javascript',
            body="document.addEventListener('keydown', function (e) {"
                 " if (e.key === 'Backspace') throw new Error('not ours'); });"))
        page.evaluate("""(src) => new Promise((ok, bad) => {
            const s = document.createElement('script');
            s.src = src; s.onload = ok; s.onerror = bad;
            document.head.appendChild(s);
        })""", FOREIGN)
        field = page.locator(f'[data-lrd-field="data-cable-ft-{box}-{key}"]')
        field.click()
        page.keyboard.type('25')
        page.keyboard.press('Backspace')
        page.keyboard.press('Backspace')
        page.wait_for_timeout(300)
        foreign = [b['details'] for b in seen['logged']]
        assert len(foreign) == 2, foreign
        for d in foreign:
            assert d['message'] == 'Script error.', d
            assert (d['filename'], d['lineno'], d['colno'], d['stack']) == ('', 0, 0, ''), d
            assert d['opaque'] is True and d['actionable'] is False, d
            assert 'outside the app' in d['origin'], d
            assert d['lastInput']['key'] == 'Backspace', d
            assert d['lastInput']['field'] == f'data-cable-ft-{box}-{key}', d
        # the length still saves, as it did for the owner
        page.keyboard.press('Enter')
        _quiet(page)
        assert page.evaluate(STORED_JS, [box, key]) is None
        # A throw in the app's own origin keeps its file and line, untagged.
        seen['logged'].clear()
        own = f'{e2e_server}/static/js/__test_throws.js'
        page.route(own, lambda route: route.fulfill(
            status=200, content_type='text/javascript',
            body="setTimeout(function () { throw new Error('ours'); }, 0);"))
        page.evaluate("""(src) => new Promise((ok, bad) => {
            const s = document.createElement('script');
            s.src = src; s.onload = ok; s.onerror = bad;
            document.head.appendChild(s);
        })""", own)
        page.wait_for_timeout(300)
        ours = [b['details'] for b in seen['logged']]
        assert len(ours) == 1, ours
        assert 'ours' in ours[0]['message'], ours
        assert ours[0]['filename'] and ours[0]['lineno'] > 0, ours
        assert 'opaque' not in ours[0] and 'actionable' not in ours[0], ours
    finally:
        context.close()
