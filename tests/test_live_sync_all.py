"""Every change to the show reaches every page (2026-11-10).

Owner, 2026-11-09: once the app is running it is "treated like a live
service". test_live_sync.py covers the whole-project replaces (a show
opened, File > New, Undo, Redo, a group change, a guide). This module
covers the rest:

1. A screen added, duplicated, pasted or deleted on one page shows on the
   others. The server sent layer_added / layer_deleted, which no page read.
2. A processor, a canvas or the port map changed on one page shows on the
   others. Their project_updated carried no mark and every page dropped it.
3. Everything saved through POST /api/project (the Screens list's order,
   distros, the binder, the pull sheet, the cable stock, the raster after
   New) shows on the others. It sent nothing at all.
   Every one of these now says `_replace` with reason 'edit' and the page
   that made it (routes_project emit_project_edited); the others take the
   show in as the same show (app-core _onProjectEdited), with the changes
   made elsewhere as one undo step of their own (_recordForeignStep).
4. Two pages opening a show within a moment of each other both end on the
   one the server kept: a file open's late answer is let go once another
   page's replace has been taken in, as an undo's already was.
5. One guide at a time, for every page: the server knows which page's
   guide holds the show and refuses show changes from any other page while
   that page's socket is up; the page says so and changes nothing. The
   guide's page closing frees the show at once.

Run locally (each session takes its own free port):
    python -m pytest tests/test_live_sync_all.py -v --browser chromium
"""

import json
import time
import urllib.request

import pytest

import app as app_module
import routes_project

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


GUIDE_REFUSAL = 'A guide is running in another window. Finish it there first.'
QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
CLIENT_LOG = (
    "window.__clog = [];"
    "(function () { const send = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);"
    " navigator.sendBeacon = (u, b) => { try { b.text().then(t => { const j = JSON.parse(t);"
    " window.__clog.push({ action: j.action, details: j.details }); }); } catch (e) {}"
    " return send ? send(u, b) : true; }; })();"
)
UNAVAILABLE = json.dumps({'ok': False, 'cancelled': True})
# A red toast the page showed (app-presets _toast logs each one).
SAID = ("(t) => (window.__clog || []).some(e => e.action === 'toast_error'"
        " && (e.details || {}).message === t)")


# ── the server's messages ─────────────────────────────────────────────────

def _marks(sock):
    return [(r['args'][0]['_replace'], r['args'][0].get('_rev'))
            for r in sock.get_received()
            if r['name'] == 'project_updated' and '_replace' in r['args'][0]]


def _edits(sock):
    return [m for m, _ in _marks(sock) if m['reason'] == 'edit']


PAGE_A = {'X-LRD-Page': 'page-a'}


def test_every_change_to_the_show_tells_the_other_pages(client):
    sock = app_module.socketio.test_client(app_module.app)
    try:
        sock.get_received()
        # a screen added, then deleted: gap 1
        layer = client.post('/api/layer/add', json={'name': 'NEW'}, headers=PAGE_A).get_json()
        got = _edits(sock)
        assert [m['client'] for m in got] == ['page-a'], got
        client.delete(f"/api/layer/{layer['id']}", headers=PAGE_A)
        assert [m['client'] for m in _edits(sock)] == ['page-a']
        # a processor, a canvas: gap 2
        r = client.post('/api/processors', json={'deviceId': 'novastar-h9'}, headers=PAGE_A)
        assert r.status_code == 201
        assert len(_edits(sock)) == 1
        client.post('/api/canvas', json={'name': 'Canvas 2'}, headers=PAGE_A)
        assert len(_edits(sock)) == 1
        # POST /api/project: the distros, the order of the screens: gap 3
        client.post('/api/project', json={'distros': [{'id': 'd1', 'name': 'DISTRO 1'}]}, headers=PAGE_A)
        assert len(_edits(sock)) == 1
        # ... and nothing at all when nothing changed (a page's load
        # re-sends a raster the show already has)
        proj = client.get('/api/project').get_json()
        client.post('/api/project', json={'raster_width': proj['raster_width'],
                                          'raster_height': proj['raster_height'],
                                          'keep_pristine': True})
        assert _edits(sock) == []
        # a request from no page is every page's news
        client.post('/api/beaches', json={'name': 'SL'})
        assert [m['client'] for m in _edits(sock)] == ['']
    finally:
        sock.disconnect()


def test_messages_are_numbered_and_a_read_says_the_newest(client):
    sock = app_module.socketio.test_client(app_module.app)
    try:
        sock.get_received()
        client.post('/api/layer/add', json={'name': 'ONE'})
        client.post('/api/layer/add', json={'name': 'TWO'})
        revs = [rev for _, rev in _marks(sock)]
        assert len(revs) == 2 and revs[1] == revs[0] + 1, revs
        r = client.get('/api/project')
        assert int(r.headers['X-Project-Rev']) == revs[1]
    finally:
        sock.disconnect()


def test_a_blanked_cabinet_reaches_the_other_pages(client_with_layer):
    client = client_with_layer
    layer = client.get('/api/project').get_json()['layers'][-1]
    sock = app_module.socketio.test_client(app_module.app)
    try:
        sock.get_received()
        client.post(f"/api/layer/{layer['id']}/panel/{layer['panels'][0]['id']}/toggle")
        got = [r['args'][0] for r in sock.get_received() if r['name'] == 'layer_updated']
        assert got and got[0]['panels'][0]['blank'] is True
    finally:
        sock.disconnect()


# ── one guide at a time ───────────────────────────────────────────────────

def _guide_socket(page='page-g'):
    return app_module.socketio.test_client(app_module.app, query_string=f'page={page}')


def test_a_guide_holds_the_show_while_its_page_is_up(client_with_layer):
    client = client_with_layer
    guide = _guide_socket()
    other = app_module.socketio.test_client(app_module.app)
    try:
        proj = client.get('/api/project').get_json()
        layer_id = proj['layers'][0]['id']
        r = client.put('/api/project?reason=guide', json=dict(proj, name='Demo'),
                       headers={'X-LRD-Page': 'page-g'})
        assert r.status_code == 200
        assert client.get('/api/guide').get_json() == {'page': 'page-g'}
        assert {'page': 'page-g'} in [r['args'][0] for r in other.get_received()
                                      if r['name'] == 'guide_state']
        before = client.get('/api/project').get_json()
        # another page: refused, whatever it is, and nothing changes
        for method, path, body in (
                ('put', '/api/project?reason=open', dict(proj, name='Opened')),
                ('post', '/api/project/new?reason=new', None),
                ('put', '/api/project?reason=undo', proj),
                ('put', f'/api/layer/{layer_id}', {'name': 'RENAMED'}),
                ('post', '/api/layer/add', {'name': 'ADDED'}),
                ('post', '/api/project', {'name': 'Posted'}),
                ('post', '/api/processors', {'deviceId': 'novastar-h9'})):
            r = getattr(client, method)(path, json=body, headers={'X-LRD-Page': 'page-b'})
            assert r.status_code == 409, (path, r.status_code)
            assert r.headers.get('X-LRD-Guide') == 'running'
            assert r.get_json()['error'] == GUIDE_REFUSAL
        assert client.get('/api/project').get_json() == before
        # its reads, and the reads that look like writes, still answer
        assert client.post('/api/port-assignments/resolve', json={'screens': []},
                           headers={'X-LRD-Page': 'page-b'}).status_code == 200
        assert client.post('/api/project/unsaved', json={'unsaved': True},
                           headers={'X-LRD-Page': 'page-b'}).status_code == 200
        # the guide's own page goes on, and so does a script
        assert client.put(f'/api/layer/{layer_id}', json={'name': 'GUIDE STEP'},
                          headers={'X-LRD-Page': 'page-g'}).status_code == 200
        assert client.put(f'/api/layer/{layer_id}', json={'name': 'SCRIPT'}).status_code == 200
        # the guide ends: free again
        r = client.put('/api/project?reason=guide_end', json=proj, headers={'X-LRD-Page': 'page-g'})
        assert r.status_code == 200
        assert client.get('/api/guide').get_json() == {'page': None}
        assert client.put('/api/project?reason=open', json=dict(proj, name='Opened'),
                          headers={'X-LRD-Page': 'page-b'}).status_code == 200
    finally:
        other.disconnect()
        if guide.is_connected():
            guide.disconnect()


def test_the_guide_s_page_closing_frees_the_show_at_once(client):
    guide = _guide_socket()
    try:
        proj = client.get('/api/project').get_json()
        client.put('/api/project?reason=guide', json=proj, headers={'X-LRD-Page': 'page-g'})
        assert client.put('/api/project?reason=open', json=proj,
                          headers={'X-LRD-Page': 'page-b'}).status_code == 409
    finally:
        guide.disconnect()
    assert routes_project.guide_page() is None
    assert client.put('/api/project?reason=open', json=dict(proj, name='After'),
                      headers={'X-LRD-Page': 'page-b'}).status_code == 200
    assert client.get('/api/project').get_json()['name'] == 'After'


def test_a_guide_whose_page_has_no_socket_holds_nothing(client):
    """A guide's request from a page the server cannot see (no socket):
    nothing to wait for, so nothing is held."""
    proj = client.get('/api/project').get_json()
    client.put('/api/project?reason=guide', json=proj, headers={'X-LRD-Page': 'page-gone'})
    assert routes_project.guide_page() is None
    assert client.put('/api/project?reason=open', json=proj,
                      headers={'X-LRD-Page': 'page-b'}).status_code == 200


# ── in the browser: two pages on one server ───────────────────────────────

def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _post(url, path, body=None):
    data = b'' if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url + path, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with _opener().open(req, timeout=10) as reply:
        assert reply.status in (200, 201)
        return json.loads(reply.read().decode('utf-8'))


def _get(url, path):
    with _opener().open(url + path, timeout=10) as reply:
        return json.loads(reply.read().decode('utf-8'))


def _server_project(url):
    return _get(url, '/api/project')


def _server_names(url):
    return [l['name'] for l in _server_project(url)['layers']]


def _seed_show(url):
    _post(url, '/api/project/new')
    _post(url, '/api/layer/add', {'name': 'LEFT', 'columns': 4, 'rows': 3,
                                  'cabinet_width': 128, 'cabinet_height': 128,
                                  'offset_x': 1100, 'offset_y': 0})
    _post(url, '/api/layer/add', {'name': 'RIGHT', 'columns': 4, 'rows': 3,
                                  'cabinet_width': 128, 'cabinet_height': 128,
                                  'offset_x': 1700, 'offset_y': 0})
    _post(url, '/api/project', {'name': 'Before Show'})
    assert _server_names(url) == ['Screen1', 'LEFT', 'RIGHT']


def _context(pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(QUIET + CLIENT_LOG)
    for name in ('save-file', 'open-file', 'select-directory'):
        context.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json', body=UNAVAILABLE))
    return context


def _watch(pg, allow_409=False):
    problems = []
    pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))

    def console(m):
        if m.type != 'error' or m.text.startswith('Failed to load resource'):
            return
        # a page reloading or closing: its socket's last frame crossed the close
        if 'Data frame received after close' in m.text:
            return
        problems.append('console: ' + m.text)
    pg.on('console', console)

    def response(r):
        if '/api/' not in r.url or r.status < 400:
            return
        if '/api/native-dialog/' in r.url or '/api/panel-catalog/refresh' in r.url:
            return
        if allow_409 and r.status == 409 and r.headers.get('x-lrd-guide') == 'running':
            return
        problems.append(f'{r.status} {r.url}')
    pg.on('response', response)
    return problems


def _open(context, url, allow_409=False):
    pg = context.new_page()
    problems = _watch(pg, allow_409)
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.wait_for_timeout(800)
    pg.evaluate("() => { window.__sameDocument = true; }")
    return pg, problems


def _names(pg):
    return pg.evaluate("() => window.app.project.layers.map(l => l.name)")


def _not_reloaded(pg):
    return pg.evaluate("() => window.__sameDocument === true")


def _wait(pg, js, arg=None, timeout=10000):
    pg.wait_for_function(js, arg=arg, timeout=timeout)


def _settled(url, want, timeout=10.0):
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = _server_project(url)
        if want(got):
            return got
        time.sleep(0.2)
    raise AssertionError(f'the server never got there: {[l["name"] for l in got["layers"]]}')


def _eventually(pg, js, want, timeout=10.0):
    """`js` read on the page comes to `want` (compared as data, so the key
    order of either side does not matter)."""
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = pg.evaluate(js)
        if got == want:
            return
        time.sleep(0.1)
    raise AssertionError(f'{js} reads {got!r}, not {want!r}')


def _quiet(*pages, ms=1200):
    """Let every message and read in flight land."""
    pages[0].wait_for_timeout(ms)


def _history(pg):
    return pg.evaluate("() => ({ index: window.app.historyIndex, length: window.app.history.length,"
                       " last: window.app.history[window.app.historyIndex].action })")


def _log(pg, prefix):
    return pg.evaluate("(p) => (window.__clog || []).filter(e => e.action.startsWith(p))"
                       ".map(e => [e.action, (e.details || {}).reason || null])", prefix)


def _two_pages(pw_browser, url, allow_409=False):
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    a, pa = _open(ctx_a, url, allow_409)
    b, pb = _open(ctx_b, url, allow_409)
    return (ctx_a, ctx_b), a, b, pa, pb


def test_screens_added_duplicated_pasted_and_deleted_show_on_the_other_page(e2e_server, pw_browser):
    _seed_show(e2e_server)
    (ctx_a, ctx_b), a, b, pa, pb = _two_pages(pw_browser, e2e_server)
    try:
        b.evaluate("() => window.app.selectLayer(window.app.project.layers[1])")
        b.locator('#view-tabs .view-tab[data-mode="power"]').click()
        before_b = _history(b)
        # Add Screen
        a.evaluate("() => window.app.addLayer()")
        _settled(e2e_server, lambda p: len(p['layers']) == 4)
        added = _server_names(e2e_server)[-1]
        _wait(b, "(n) => window.app.project.layers.map(l => l.name).includes(n)", added)
        # Duplicate
        a.evaluate("() => window.app.duplicateLayer(window.app.project.layers.find(l => l.name === 'LEFT'))")
        _settled(e2e_server, lambda p: len(p['layers']) == 5)
        # Copy and Paste
        a.evaluate("() => { const app = window.app; app.selectLayer(app.project.layers.find(l => l.name === 'RIGHT'));"
                   " app.copyLayer(); app.pasteLayer(); }")
        srv = _settled(e2e_server, lambda p: len(p['layers']) == 6)
        want = [l['name'] for l in srv['layers']]
        _wait(b, "(w) => window.app.project.layers.map(l => l.name).join('|') === w.join('|')", want)
        _quiet(a)
        # the page shows them as the server has them: the pasted screen's
        # place included, which the paste's own save set after the add
        mine = {l['id']: (l['offset_x'], l['offset_y']) for l in b.evaluate("() => window.app.project.layers")}
        theirs = {l['id']: (l['offset_x'], l['offset_y']) for l in _server_project(e2e_server)['layers']}
        assert mine == theirs
        # in the Screens list too, its own tab and selection kept
        listed = b.evaluate("() => [...document.querySelectorAll('#layers-list .layer-name-input')]"
                            ".map(i => i.value).reverse()")
        assert listed == want, listed
        assert b.evaluate("() => window.canvasRenderer.viewMode") == 'power'
        assert b.evaluate("() => window.app.currentLayer.name") == 'LEFT'
        # Delete on the first page
        a.evaluate("() => { const app = window.app; app.selectLayer(app.project.layers[app.project.layers.length - 1]);"
                   " app.deleteCurrentLayer(); }")
        srv = _settled(e2e_server, lambda p: len(p['layers']) == 5)
        want = [l['name'] for l in srv['layers']]
        _wait(b, "(w) => window.app.project.layers.map(l => l.name).join('|') === w.join('|')", want)
        # the other page's changes are one step here: Undo takes them back
        # (on every page), Redo brings them again
        st = _history(b)
        assert st['length'] == before_b['length'] + 1, (before_b, st)
        assert st['last'] == 'Changes From Another Page'
        b.evaluate("() => window.app.undo()")
        _settled(e2e_server, lambda p: [l['name'] for l in p['layers']] == ['Screen1', 'LEFT', 'RIGHT'])
        _wait(a, "() => window.app.project.layers.length === 3")
        b.evaluate("() => window.app.redo()")
        _settled(e2e_server, lambda p: [l['name'] for l in p['layers']] == want)
        _wait(a, "(w) => window.app.project.layers.map(l => l.name).join('|') === w.join('|')", want)
        assert _not_reloaded(a) and _not_reloaded(b)
        assert ('socket_project_replaced', 'edit') in [tuple(x) for x in _log(b, 'socket_project_replaced')]
        assert ('socket_project_replaced', 'edit') not in [tuple(x) for x in _log(a, 'socket_project_replaced')]
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()


def test_processors_canvases_and_ports_show_on_the_other_page(e2e_server, pw_browser):
    _seed_show(e2e_server)
    (ctx_a, ctx_b), a, b, pa, pb = _two_pages(pw_browser, e2e_server)
    try:
        a.evaluate("() => window.app._processorAddRequest('/api/processors', 'POST',"
                   " { deviceId: 'novastar-h9' }, 'Add Processor')")
        _settled(e2e_server, lambda p: len(p.get('processors') or []) == 1)
        # the tray's tree is read through its own route: read again here
        _wait(b, "() => (window.app._processorsResolved || []).length === 1")
        assert b.evaluate("() => window.app.project.processors.length") == 1
        a.evaluate("() => window.app.addCanvas()")
        _settled(e2e_server, lambda p: len(p['canvases']) == 2)
        _wait(b, "() => window.app.project.canvases.length === 2")
        # a card in the first slot, then a port placed on it (the port map)
        pid = _server_project(e2e_server)['processors'][0]['id']
        a.evaluate("(pid) => window.app._processorRequest(`/api/processors/${pid}/slots/0`, 'PUT',"
                   " { deviceId: 'novastar-card-h-20xrj45' }, 'Set Card')", pid)
        srv = _settled(e2e_server, lambda p: bool(p['processors'][0]['slots'][0].get('card')))
        card = srv['processors'][0]['slots'][0]['card']
        _wait(b, "() => !!window.app.project.processors[0].slots[0].card")
        layer = srv['layers'][1]
        a.evaluate("([card, layer]) => window.app._assignmentRequest('/api/port-assignments/pin', 'POST',"
                   " { cardId: card, port: 1, layerId: layer, index: 0 }, null, 'Pin Port')",
                   [card['id'], layer['id']])
        srv = _settled(e2e_server, lambda p: bool((p.get('port_assignments') or {}).get('pins')))
        _eventually(b, "() => (window.app.project.port_assignments || {}).pins || null",
                    srv['port_assignments']['pins'])
        assert _not_reloaded(b)
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()


def test_everything_saved_through_the_project_post_shows_on_the_other_page(e2e_server, pw_browser):
    _seed_show(e2e_server)
    (ctx_a, ctx_b), a, b, pa, pb = _two_pages(pw_browser, e2e_server)
    try:
        # the Screens list's order
        a.evaluate("() => window.app.moveLayerWithinCanvas(window.app.project.layers[2].id, 1)")
        srv = _settled(e2e_server, lambda p: [l['name'] for l in p['layers']] != ['Screen1', 'LEFT', 'RIGHT'])
        order = [l['name'] for l in srv['layers']]
        _wait(b, "(w) => window.app.project.layers.map(l => l.name).join('|') === w.join('|')", order)
        # a distro
        a.evaluate("() => window.app.addDistro({ name: 'SR DISTRO' })")
        _settled(e2e_server, lambda p: any(d.get('name') == 'SR DISTRO' for d in p.get('distros') or []))
        _wait(b, "() => window.app.getDistros().some(d => d.name === 'SR DISTRO')")
        # the binder
        a.evaluate("() => window.app.setBinderField('venue', 'The Arena')")
        _settled(e2e_server, lambda p: (p.get('binder') or {}).get('venue') == 'The Arena')
        _wait(b, "() => window.app.getBinderInfo().venue === 'The Arena'")
        # the pull sheet's edits and the cable stock (its own POST queue)
        a.evaluate("""() => { const app = window.app;
            app.project.pullSheetEdits = { positions: { 'p-test': { qty: 3 } } };
            app._postPullSheetState(['pullSheetEdits']); }""")
        _settled(e2e_server, lambda p: 'p-test' in ((p.get('pullSheetEdits') or {}).get('positions') or {}))
        _wait(b, "() => !!((window.app.project.pullSheetEdits || {}).positions || {})['p-test']")
        a.evaluate("() => window.app.setCableStock({ ft: { all: [5, 10, 25] } })")
        stock = _settled(e2e_server, lambda p: bool(p.get('cableStock')))['cableStock']
        _eventually(b, "() => window.app.project.cableStock", stock)
        assert _not_reloaded(b)
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()


def test_the_raster_a_new_show_gets_shows_on_the_other_page(e2e_server, pw_browser):
    _seed_show(e2e_server)
    (ctx_a, ctx_b), a, b, pa, pb = _two_pages(pw_browser, e2e_server)
    try:
        # the first page's own raster for a new show: not the server's
        # default, and not the second page's preference
        a.evaluate("() => { const p = window.app.getPreferences(); p.rasterWidth = 2560;"
                   " p.rasterHeight = 1440; window.app.getPreferences = () => p;"
                   " window.app.createNewProject(); }")
        _settled(e2e_server, lambda p: p.get('name') == 'Untitled Project')
        # its raster save, which a slow machine can hold a while
        a.evaluate("async () => { await new Promise(r => setTimeout(r, 300));"
                   " await window.app._layerSavesSettled(); }")
        _settled(e2e_server, lambda p: p.get('raster_width') == 2560)
        _wait(b, "() => window.app.project.name === 'Untitled Project' && window.app.project.raster_width === 2560"
                 " && window.canvasRenderer.pixelRasterWidth === 2560")
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()


def test_a_change_elsewhere_waits_for_this_page_s_own_save(e2e_server, pw_browser):
    """The other page's change lands while this page's own save is still
    on its way: taken in then, its copy of the show would not hold this
    page's save, and that save's echo is this page's own, so the page would
    lose its own change. It waits, and reads the show once its save has
    landed."""
    _seed_show(e2e_server)
    (ctx_a, ctx_b), a, b, pa, pb = _two_pages(pw_browser, e2e_server)
    held = []

    def hold(route):
        if route.request.method == 'POST' and 'B DISTRO' in (route.request.post_data or ''):
            held.append(route)   # not sent yet: the server has not seen it
            return
        route.continue_()
    ctx_b.route('**/api/project', hold)
    try:
        b.evaluate("() => window.app.addDistro({ name: 'B DISTRO' })")
        deadline = time.time() + 10
        while not held and time.time() < deadline:
            b.wait_for_timeout(50)
        assert held, 'the distro save never went'
        # the other page's change, made before the server has this one
        a.evaluate("() => window.app.addLayer()")
        _settled(e2e_server, lambda p: len(p['layers']) == 4)
        _wait(b, "() => (window.__clog || []).some(e => e.action === 'socket_project_edited_waits_for_own')")
        # meanwhile the page still shows its own distro
        assert b.evaluate("() => window.app.getDistros().some(d => d.name === 'B DISTRO')")
        held[0].continue_()
        _wait(b, "() => window.app.project.layers.length === 4")
        _settled(e2e_server, lambda p: any(d.get('name') == 'B DISTRO' for d in p.get('distros') or []))
        b.wait_for_timeout(800)
        assert b.evaluate("() => window.app.getDistros().some(d => d.name === 'B DISTRO')")
        assert b.evaluate("() => window.app.project.layers.length") == 4
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()


def _open_show(pg, name, names):
    pg.evaluate("""async ([name, names]) => {
        const app = window.app;
        const file = JSON.parse(app.serializeProjectForFile(JSON.parse(JSON.stringify(app.project))));
        file.name = name;
        file.layers = file.layers.slice(0, names.length);
        file.layers.forEach((l, i) => { l.name = names[i]; });
        file.groups = [];
        file.layers.forEach(l => { delete l.group_id; });
        app._openProjectData(file, { source: 'file' });
    }""", [name, names])


def test_two_pages_opening_at_once_both_end_on_the_show_the_server_kept(e2e_server, pw_browser):
    """Gap 4: the second page's open lands on the server first and its
    answer is slow; the first page's open lands after it. The slow answer
    must not put the second page's show back over the one the server
    kept."""
    _seed_show(e2e_server)
    (ctx_a, ctx_b), a, b, pa, pb = _two_pages(pw_browser, e2e_server)
    try:
        b.evaluate("""() => { const f = window.fetch; window.__hold = true;
            window.fetch = function (u, i) { const p = f.call(this, u, i);
              if (String(u).includes('reason=open'))
                return p.then(r => new Promise(res => { const t = setInterval(() => {
                  if (!window.__hold) { clearInterval(t); res(r); } }, 20); }));
              return p; }; }""")
        _open_show(b, 'B Show', ['B ONE', 'B TWO'])
        _settled(e2e_server, lambda p: p['name'] == 'B Show')
        _open_show(a, 'A Show', ['A ONE'])
        _settled(e2e_server, lambda p: p['name'] == 'A Show')
        _wait(b, "() => window.app.project.name === 'A Show'")
        b.evaluate("() => { window.__hold = false; }")
        _quiet(b, ms=1500)
        assert _server_project(e2e_server)['name'] == 'A Show'
        assert b.evaluate("() => window.app.project.name") == 'A Show'
        assert _names(b) == ['A ONE']
        assert a.evaluate("() => window.app.project.name") == 'A Show'
        assert b.evaluate("() => (window.__clog || []).some(e => e.action === 'open_answer_after_other_page')")
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()


def _start_guide(pg, url):
    deadline = time.time() + 30
    pg.evaluate("() => { window.QuickStart.setSpeed(4); window.QuickStart.start(); }")
    st = None
    while time.time() < deadline:
        st = pg.evaluate("""() => { const q = window.QuickStart.state();
            return { visible: q.visible,
                     layers: window.app.project.layers.map(l => l.name) }; }""")
        if st['visible'] and 'DEMO WALL' in st['layers']:
            break
        time.sleep(0.25)
    else:
        raise AssertionError(f'the guide did not come up: {st}')
    _settled(url, lambda p: 'DEMO WALL' in [l['name'] for l in p['layers']], timeout=20)



def test_another_page_cannot_change_the_show_while_a_guide_runs(e2e_server, pw_browser):
    """Gap 5: a guide on one page; the other page, in another browser,
    tries File > Open, New, Undo and a screen's edit. Each is refused
    with the message and the server's show stays the guide's. The guide's
    page closing frees the show at once."""
    _seed_show(e2e_server)
    ctx_guide, ctx_other = _context(pw_browser), _context(pw_browser)
    try:
        other, problems = _open(ctx_other, e2e_server, allow_409=True)
        guide, more = _open(ctx_guide, e2e_server)
        _start_guide(guide, e2e_server)
        _wait(other, "() => window.app.project.layers.some(l => l.name === 'DEMO WALL')")
        _wait(other, "() => window.app._guideRunningElsewhere()")
        demo = _server_project(e2e_server)
        _open_show(other, 'Opened Show', ['UPSTAGE'])
        _wait(other, SAID, GUIDE_REFUSAL)
        other.evaluate("() => { window.app.createNewProject(); window.app.undo(); }")
        _quiet(other, ms=1000)
        now = _server_project(e2e_server)
        assert now['name'] == demo['name'] and [l['name'] for l in now['layers']] == \
            [l['name'] for l in demo['layers']]
        assert other.evaluate("() => window.app.project.name") == demo['name']
        # a screen's own edit: the server refuses it, and the page puts
        # the guide's screen back
        wall = next(l for l in demo['layers'] if l['name'] == 'DEMO WALL')
        other.evaluate("(id) => { const app = window.app; const l = app.project.layers.find(x => x.id === id);"
                       " l.name = 'HIJACKED'; app._putLayer(l.id, { name: 'HIJACKED' }); }", wall['id'])
        _wait(other, "(id) => window.app.project.layers.find(x => x.id === id).name === 'DEMO WALL'", wall['id'])
        assert 'HIJACKED' not in _server_names(e2e_server)
        # the guide never saw any of it
        assert guide.evaluate("() => window.QuickStart.state().visible")
        assert 'DEMO WALL' in _names(guide)
        assert guide.evaluate("() => (window.__clog || []).filter(e =>"
                              " e.action === 'socket_project_replaced_held_by_guide').length") == 0
        # the guide's page closes mid-guide: the show is free at once
        guide.close()
        deadline = time.time() + 5
        while time.time() < deadline and _get(e2e_server, '/api/guide')['page'] is not None:
            time.sleep(0.1)
        assert _get(e2e_server, '/api/guide') == {'page': None}
        _wait(other, "() => !window.app._guideRunningElsewhere()")
        _open_show(other, 'Opened Show', ['UPSTAGE'])
        _settled(e2e_server, lambda p: p['name'] == 'Opened Show')
        assert _not_reloaded(other)
        assert problems == [] and more == [], problems + more
    finally:
        ctx_guide.close()
        ctx_other.close()
