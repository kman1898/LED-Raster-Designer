"""Every page follows a whole-project replace (2026-11-09).

Owner, 2026-11-09: once the app is running it is "treated like a live
service". Another tab, another browser or a tablet at the computer's
address joins the show as it stands (test_live_join.py), and a screen's
edit reaches the other pages as its layer_updated echo. A show opened,
File > New, an undo or a redo, a group change, a guide's demo show and its
end replace the WHOLE project, and the server told the pages so with
`project_updated`, which they dropped: the other pages kept the old show,
and their next save wrote the old show's screen into the new one under the
same id.

Now the message carries `_replace` (routes_project _emit_project_replaced):
why, the page whose request did it (the X-LRD-Page header every page's own
requests carry) and its number for the request. Every other page takes the
project in (app-core.js _onProjectReplaced) and lands on it: its own tab;
on the same show (undo, redo, a group change) its selection by id, its
history and a field it is typing in; on another show the opening screen,
a fresh history and the new show's values. The page that asked lets its
own echo go. A save made from the show that went never reaches the server
(_putLayer), a hand on a gesture keeps the old show until it lets go, and a
page running a guide is never pulled out of it.

Run locally (each session takes its own free port):
    python -m pytest tests/test_live_sync.py -v --browser chromium
"""

import json
import time
import urllib.request

import pytest

import app as app_module

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
# The client log, as sendClientLog beacons it, kept on the page.
CLIENT_LOG = (
    "window.__clog = [];"
    "(function () { const send = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);"
    " navigator.sendBeacon = (u, b) => { try { b.text().then(t => { const j = JSON.parse(t);"
    " window.__clog.push({ action: j.action, details: j.details }); }); } catch (e) {}"
    " return send ? send(u, b) : true; }; })();"
)
UNAVAILABLE = json.dumps({'ok': False, 'cancelled': True})


# ── the server's message ──────────────────────────────────────────────────

def _replaces(sock):
    return [r['args'][0]['_replace'] for r in sock.get_received()
            if r['name'] == 'project_updated' and '_replace' in r['args'][0]]


def test_a_replace_tells_every_page_why_and_which_page_asked(client):
    sock = app_module.socketio.test_client(app_module.app)
    try:
        sock.get_received()
        proj = client.get('/api/project').get_json()
        r = client.put('/api/project?reason=undo&token=7', json=proj,
                       headers={'X-LRD-Page': 'page-a'})
        assert r.status_code == 200
        assert _replaces(sock) == [{'reason': 'undo', 'client': 'page-a', 'token': 7, 'unsaved': False}]
        client.post('/api/project/new?reason=new&token=8', headers={'X-LRD-Page': 'page-b'})
        assert _replaces(sock) == [{'reason': 'new', 'client': 'page-b', 'token': 8, 'unsaved': False}]
        # a request from no page (a script, a test): every page's news
        client.put('/api/project', json=client.get('/api/project').get_json())
        assert _replaces(sock) == [{'reason': 'restore', 'client': '', 'token': None, 'unsaved': False}]
        # a reason the server does not know reads as a plain restore
        client.put('/api/project?reason=bogus&token=x', json=client.get('/api/project').get_json())
        assert _replaces(sock) == [{'reason': 'restore', 'client': '', 'token': None, 'unsaved': False}]
        # and the message carries the project as the server stored it
        client.post('/api/project/unsaved', json={'unsaved': True})
        client.put('/api/project?reason=open', json=dict(proj, name='Carried'))
        got = [r['args'][0] for r in sock.get_received() if r['name'] == 'project_updated']
        assert got[-1]['name'] == 'Carried' and got[-1]['_replace']['unsaved'] is True
    finally:
        sock.disconnect()


def test_a_route_s_own_restatement_is_marked_as_an_edit(client):
    """A processor, a canvas or the port map restate the project through
    the same message, marked as an edit of the same show (2026-11-10:
    every page follows those too; test_live_sync_all.py)."""
    sock = app_module.socketio.test_client(app_module.app)
    try:
        sock.get_received()
        client.post('/api/canvas', json={'name': 'Canvas 2'}, headers={'X-LRD-Page': 'page-a'})
        got = [r for r in sock.get_received() if r['name'] == 'project_updated']
        assert got and all(r['args'][0]['_replace']['reason'] == 'edit'
                           and r['args'][0]['_replace']['client'] == 'page-a' for r in got)
    finally:
        sock.disconnect()


# ── in the browser: two pages on one server ───────────────────────────────

def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _post(url, path, body=None):
    data = b'' if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url + path, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with _opener().open(req, timeout=10) as reply:
        assert reply.status == 200
        return json.loads(reply.read().decode('utf-8'))


def _server_project(url):
    with _opener().open(url + '/api/project', timeout=10) as reply:
        return json.loads(reply.read().decode('utf-8'))


def _server_names(url):
    return [l['name'] for l in _server_project(url)['layers']]


def _seed_show(url):
    """A show on the server before any page opens: three screens."""
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


def _watch(pg):
    problems = []
    pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))
    pg.on('console', lambda m: problems.append('console: ' + m.text)
          if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
    pg.on('response', lambda r: problems.append(f'{r.status} {r.url}')
          if '/api/' in r.url and r.status >= 400 and '/api/native-dialog/' not in r.url
          and '/api/panel-catalog/refresh' not in r.url else None)
    return problems


def _open(context, url):
    pg = context.new_page()
    problems = _watch(pg)
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.wait_for_timeout(800)
    # set once: still there later means the page was never reloaded
    pg.evaluate("() => { window.__sameDocument = true; }")
    return pg, problems


def _names(pg):
    return pg.evaluate("() => window.app.project.layers.map(l => l.name)")


LIST_NAMES_JS = ("() => [...document.querySelectorAll('#layers-list .layer-name-input')]"
                 ".map(i => i.value).reverse()")


def _list_names(pg):
    """The Screens list as it reads on the page, bottom up (the list shows
    the newest screen on top), so in the project's order."""
    return pg.evaluate(LIST_NAMES_JS)


def _wait_list(pg, want, timeout=5.0):
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = _list_names(pg)
        if got == want:
            return
        time.sleep(0.1)
    raise AssertionError(f'the Screens list reads {got}, not {want}')


def _log(pg, prefix='socket_project_replaced'):
    return pg.evaluate("(p) => (window.__clog || []).filter(e => e.action.startsWith(p))"
                       ".map(e => [e.action, (e.details || {}).reason || null])", prefix)


def _not_reloaded(pg):
    return pg.evaluate("() => window.__sameDocument === true")


def _open_show(pg, name, names, notes=None):
    """File > Open of a show: the page's own project, renamed, its screens
    renamed (the same ids: the case where an old save would land on a new
    show's screen), the last screen left out."""
    pg.evaluate("""async ([name, names, notes]) => {
        const app = window.app;
        const file = JSON.parse(app.serializeProjectForFile(JSON.parse(JSON.stringify(app.project))));
        file.name = name;
        file.layers = file.layers.slice(0, names.length);
        file.layers.forEach((l, i) => { l.name = names[i]; });
        file.groups = [];
        file.layers.forEach(l => { delete l.group_id; });
        if (notes !== null) file.notes = notes;
        await app._openProjectData(file, { source: 'file' });
    }""", [name, names, notes])
    pg.wait_for_function("(n) => window.app.project.name === n", arg=name, timeout=10000)


def _follows(pg, name, timeout=10000):
    pg.wait_for_function("(n) => window.app.project.name === n", arg=name, timeout=timeout)


def _settled(url, want, timeout=10.0):
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = _server_project(url)
        if want(got):
            return got
        time.sleep(0.2)
    raise AssertionError(f'the server never got there: {[l["name"] for l in got["layers"]]}')


def test_a_show_opened_on_one_page_shows_on_the_other_without_a_reload(e2e_server, pw_browser):
    _seed_show(e2e_server)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, problems = _open(ctx_a, e2e_server)
        b, more = _open(ctx_b, e2e_server)
        assert _names(b) == ['Screen1', 'LEFT', 'RIGHT']
        # the other page stands on its own tab
        b.locator('#view-tabs .view-tab[data-mode="power"]').click()
        b.wait_for_timeout(300)
        _open_show(a, 'Opened Show', ['UPSTAGE', 'DOWNSTAGE'], notes='From the file')
        _follows(b, 'Opened Show')
        want = ['UPSTAGE', 'DOWNSTAGE']
        assert _server_names(e2e_server) == want
        assert _names(b) == want
        _wait_list(b, want)
        st = b.evaluate("""() => ({
            name: document.getElementById('project-name').value,
            notes: document.getElementById('project-notes').value,
            mode: window.canvasRenderer.viewMode,
            current: window.app.currentLayer ? window.app.currentLayer.name : null,
            selected: [...window.app.selectedLayerIds],
            ids: window.app.project.layers.map(l => l.id),
            history: window.app.history.length,
        })""")
        assert st['name'] == 'Opened Show' and st['notes'] == 'From the file', st
        assert st['mode'] == 'power', st
        # the opening screen, as a load lands on, and nothing that is gone
        assert st['current'] == 'UPSTAGE', st
        assert set(st['selected']) <= set(st['ids']), st
        # a fresh history: an Undo here cannot put the old show back
        assert st['history'] == 1, st
        assert _not_reloaded(b)
        # the page that opened it took its own echo as its own
        b.wait_for_timeout(500)
        assert ('socket_project_replaced', 'open') in [tuple(x) for x in _log(b)]
        mine = [tuple(x) for x in _log(a)]
        assert ('socket_project_replaced_own', 'open') in mine, mine
        assert ('socket_project_replaced', 'open') not in mine, mine
        assert _not_reloaded(a)
        # and the follower's Undo has nothing of the old show to put back
        b.evaluate("() => window.app.undo()")
        b.wait_for_timeout(800)
        assert _server_names(e2e_server) == want
        assert problems == [] and more == [], problems + more
    finally:
        ctx_a.close()
        ctx_b.close()


def test_file_new_on_one_tab_shows_on_the_other(e2e_server, pw_browser):
    _seed_show(e2e_server)
    context = _context(pw_browser)
    try:
        a, problems = _open(context, e2e_server)
        b, more = _open(context, e2e_server)
        assert _names(b) == ['Screen1', 'LEFT', 'RIGHT']
        a.locator('#menu-bar .menu-item[data-menu="file"]').click()
        a.wait_for_timeout(150)
        a.locator('#menu-file .menu-option[data-action="new"]').click()
        _follows(b, 'Untitled Project')
        b.wait_for_function("() => window.app.project.layers.map(l => l.name).join() === 'Screen1'",
                            timeout=10000)
        assert _server_names(e2e_server) == ['Screen1']
        _wait_list(b, ['Screen1'])
        assert b.evaluate("() => window.app.currentLayer && window.app.currentLayer.name") == 'Screen1'
        assert b.evaluate("() => document.getElementById('project-name').value") == 'Untitled Project'
        assert _not_reloaded(b) and _not_reloaded(a)
        assert ('socket_project_replaced', 'new') in [tuple(x) for x in _log(b)]
        assert ('socket_project_replaced', 'new') not in [tuple(x) for x in _log(a)]
        assert problems == [] and more == [], problems + more
    finally:
        context.close()


def _rename_on(pg, index, name):
    """A rename as the Screens list commits one: the save and its undo step."""
    pg.evaluate("""([i, name]) => {
        const app = window.app, l = app.project.layers[i];
        l.name = name;
        app._putLayer(l.id, { name });
        app.saveState('Rename Layer');
    }""", [index, name])


def test_an_undo_on_one_page_shows_on_the_other(e2e_server, pw_browser):
    _seed_show(e2e_server)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, problems = _open(ctx_a, e2e_server)
        b, more = _open(ctx_b, e2e_server)
        # the other page has the second screen selected
        b.evaluate("() => window.app.selectLayer(window.app.project.layers[1])")
        history_b = b.evaluate("() => window.app.history.length")
        _rename_on(a, 2, 'RIGHT RENAMED')
        # a screen's edit already reaches the other page (its echo)
        b.wait_for_function("() => window.app.project.layers[2].name === 'RIGHT RENAMED'", timeout=10000)
        a.evaluate("() => window.app.undo()")
        b.wait_for_function("() => window.app.project.layers[2].name === 'RIGHT'", timeout=10000)
        _settled(e2e_server, lambda p: [l['name'] for l in p['layers']] == ['Screen1', 'LEFT', 'RIGHT'])
        _wait_list(b, ['Screen1', 'LEFT', 'RIGHT'])
        st = b.evaluate("""() => ({
            current: window.app.currentLayer ? window.app.currentLayer.name : null,
            history: window.app.history.length,
        })""")
        # the same show: the selection by its id, and the page's own history
        assert st == {'current': 'LEFT', 'history': history_b}, st
        assert ('socket_project_replaced', 'undo') in [tuple(x) for x in _log(b)]
        assert ('socket_project_replaced', 'undo') not in [tuple(x) for x in _log(a)]
        assert _not_reloaded(b) and _not_reloaded(a)
        assert problems == [] and more == [], problems + more
    finally:
        ctx_a.close()
        ctx_b.close()


def _type_columns(pg, text):
    field = pg.locator('#screen-columns')
    field.click()
    pg.keyboard.press('Control+A')
    pg.keyboard.type(text)
    assert field.input_value() == text
    assert pg.evaluate("() => document.activeElement && document.activeElement.id") == 'screen-columns'


def test_typing_on_the_other_page_never_writes_the_old_show_over_an_opened_one(e2e_server, pw_browser):
    """The other page is mid-edit in a field when a show opens elsewhere.
    The field shows the opened show's value, and leaving the field writes
    nothing of the old show into the opened one (its screen has the same
    id)."""
    _seed_show(e2e_server)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, problems = _open(ctx_a, e2e_server)
        b, more = _open(ctx_b, e2e_server)
        assert b.evaluate("() => window.app.currentLayer.name") == 'Screen1'
        columns = _server_project(e2e_server)['layers'][0]['columns']
        assert str(columns) != '13'
        _type_columns(b, '13')
        _open_show(a, 'Opened Show', ['UPSTAGE', 'DOWNSTAGE'])
        _follows(b, 'Opened Show')
        # the field shows the opened show's screen, the typing is gone
        assert b.locator('#screen-columns').input_value() == str(columns)
        b.keyboard.press('Tab')
        b.wait_for_timeout(1500)
        srv = _server_project(e2e_server)
        assert [l['name'] for l in srv['layers']] == ['UPSTAGE', 'DOWNSTAGE']
        assert srv['layers'][0]['columns'] == columns
        assert srv['name'] == 'Opened Show'
        assert _names(b) == ['UPSTAGE', 'DOWNSTAGE']
        assert b.evaluate("() => window.app.project.layers[0].columns") == columns
        assert problems == [] and more == [], problems + more
    finally:
        ctx_a.close()
        ctx_b.close()


def test_typing_on_the_other_page_survives_an_undo_and_lands_on_its_screen(e2e_server, pw_browser):
    """The same show: an undo elsewhere leaves the other page's half-typed
    field as typed, and Enter commits it to its screen in the restored
    show, the undo kept."""
    _seed_show(e2e_server)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, problems = _open(ctx_a, e2e_server)
        b, more = _open(ctx_b, e2e_server)
        _rename_on(a, 2, 'RIGHT RENAMED')
        b.wait_for_function("() => window.app.project.layers[2].name === 'RIGHT RENAMED'", timeout=10000)
        assert b.evaluate("() => window.app.currentLayer.name") == 'Screen1'
        _type_columns(b, '13')
        a.evaluate("() => window.app.undo()")
        b.wait_for_function("() => window.app.project.layers[2].name === 'RIGHT'", timeout=10000)
        assert b.locator('#screen-columns').input_value() == '13'
        b.keyboard.press('Enter')
        srv = _settled(e2e_server, lambda p: p['layers'][0]['columns'] == 13)
        assert [l['name'] for l in srv['layers']] == ['Screen1', 'LEFT', 'RIGHT']
        assert b.evaluate("() => window.app.project.layers[0].columns") == 13
        a.wait_for_function("() => window.app.project.layers[0].columns === 13", timeout=10000)
        assert problems == [] and more == [], problems + more
    finally:
        ctx_a.close()
        ctx_b.close()


def _to_client(pg, layer_id, wx, wy):
    pt = pg.evaluate("""([id, wx, wy]) => {
        const app = window.app, r = window.canvasRenderer;
        const l = app.project.layers.find(x => x.id === id);
        const c = (app.project.canvases || []).find(x => x.id === l.canvas_id) || {};
        const rect = r.canvas.getBoundingClientRect();
        const x = (c.workspace_x || 0) + l.offset_x + wx, y = (c.workspace_y || 0) + l.offset_y + wy;
        return {x: rect.left + x * r.zoom + r.panX, y: rect.top + y * r.zoom + r.panY};
    }""", [layer_id, wx, wy])
    return pt['x'], pt['y']


def test_a_drag_under_way_keeps_its_show_until_it_lets_go_and_writes_nothing(e2e_server, pw_browser):
    _seed_show(e2e_server)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, problems = _open(ctx_a, e2e_server)
        b, more = _open(ctx_b, e2e_server)
        layer = _server_project(e2e_server)['layers'][1]
        before = (layer['offset_x'], layer['offset_y'])
        # Shift+drag moves the selected screen (canvas-input.js)
        b.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))",
                   layer['id'])
        sx, sy = _to_client(b, layer['id'], 100, 100)
        b.mouse.move(sx, sy)
        b.keyboard.down('Shift')
        b.mouse.down()
        b.mouse.move(sx + 20, sy + 10, steps=4)
        b.wait_for_function("() => (window.__clog || []).some(e => e.action === 'layer_drag_start')",
                            timeout=5000)
        _open_show(a, 'Opened Show', ['UPSTAGE', 'DOWNSTAGE'])
        b.wait_for_function("() => (window.__clog || []).some(e => e.action"
                            " === 'socket_project_replaced_held_for_gesture')", timeout=10000)
        # under the hand: the show it was dragging
        assert b.evaluate("() => window.app.project.name") == 'Before Show'
        b.mouse.move(sx + 80, sy + 40, steps=6)
        b.mouse.up()
        b.keyboard.up('Shift')
        _follows(b, 'Opened Show')
        b.wait_for_timeout(1500)
        # the drag's own save was made, of the show that went, and dropped
        assert b.evaluate("() => (window.__clog || []).some(e => e.action"
                          " === 'layer_put_dropped_show_replaced')")
        srv = _server_project(e2e_server)
        assert [l['name'] for l in srv['layers']] == ['UPSTAGE', 'DOWNSTAGE']
        moved = next(l for l in srv['layers'] if l['id'] == layer['id'])
        assert (moved['offset_x'], moved['offset_y']) == before
        assert _names(b) == ['UPSTAGE', 'DOWNSTAGE']
        mine = next(l for l in b.evaluate("() => window.app.project.layers") if l['id'] == layer['id'])
        assert (mine['offset_x'], mine['offset_y']) == before
        assert problems == [] and more == [], problems + more
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
                     stash: !!localStorage.getItem('lrd_tour_saved_world'),
                     layers: window.app.project.layers.map(l => l.name) }; }""")
        if st['visible'] and st['stash'] and 'DEMO WALL' in st['layers']:
            break
        time.sleep(0.25)
    else:
        raise AssertionError(f'the guide did not come up: {st}')
    _settled(url, lambda p: 'DEMO WALL' in [l['name'] for l in p['layers']], timeout=20)


def test_a_page_running_a_guide_is_never_pulled_out_of_it(e2e_server, pw_browser):
    """The guide runs on one device; the other follows it onto its demo
    show (and says so). A show it tries to open meanwhile is refused
    (2026-11-10: one guide at a time on the server, test_live_sync_all.py),
    so the guide's page stays on the guide. When the guide ends every page
    and the server agree."""
    _seed_show(e2e_server)
    ctx_guide, ctx_other = _context(pw_browser), _context(pw_browser)
    try:
        other, problems = _open(ctx_other, e2e_server)
        guide, more = _open(ctx_guide, e2e_server)
        _start_guide(guide, e2e_server)
        other.wait_for_function("() => window.app.project.layers.some(l => l.name === 'DEMO WALL')",
                                timeout=10000)
        assert ('socket_project_replaced', 'guide') in [tuple(x) for x in _log(other)]
        other.wait_for_function("() => window.app._guideRunningElsewhere()", timeout=10000)
        opened = other.evaluate("""async () => {
            const app = window.app;
            const file = JSON.parse(app.serializeProjectForFile(JSON.parse(JSON.stringify(app.project))));
            file.name = 'Opened Show';
            return await app._openProjectData(file, { source: 'file' });
        }""")
        assert opened is False
        other.wait_for_function("() => (window.__clog || []).some(e => e.action"
                                " === 'guide_elsewhere_refused')", timeout=10000)
        assert 'DEMO WALL' in _server_names(e2e_server)
        assert guide.evaluate("() => window.QuickStart.state().visible")
        assert 'DEMO WALL' in _names(guide)
        guide.evaluate("() => window.QuickStart.end()")
        guide.wait_for_function("() => !localStorage.getItem('lrd_tour_saved_world')", timeout=20000)
        guide.wait_for_timeout(1500)
        srv = _server_names(e2e_server)
        assert 'DEMO WALL' not in srv
        other.wait_for_function("(w) => window.app.project.layers.map(l => l.name).join('|') === w.join('|')",
                                arg=srv, timeout=10000)
        assert _names(guide) == srv
        assert _not_reloaded(other) and _not_reloaded(guide)
        assert problems == [] and more == [], problems + more
    finally:
        ctx_guide.close()
        ctx_other.close()
