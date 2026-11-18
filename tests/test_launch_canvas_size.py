"""A relaunch keeps the Canvas Size the Preferences give the startup show (1.7.0).

Owner, 2026-11-18, on 1.7.0-beta.6: "Canvas 1 went from 4k to 1080p when
i added a screen to canvas 2". Preferences said 3840 x 2160.

What happened: on a launch the page gives the pristine startup show the
Preferences (app-client-props loadClientSideProperties), Canvas Size
included, and sends it to the server with `keep_pristine`. Since the
follow rule (2026-11-10, a page joining a show writes nothing back) that
pass runs inside loadProject's follow pass, so the send was refused
(`follow_write_refused` POST /api/project) and the server kept its
1920 x 1080. The page showed 3840 x 2160 until the first canvas answer
replaced its copy: + Add Canvas made Canvas 2 beside a 1920 wide
Canvas 1, and Canvas 1 read 1920 x 1080 from then on.

Now the page keeps the send it may not make inside the follow pass and
makes it right after, only where the server's copy differs: the launch
page writes the Preferences' size once, and a page joining a show that
already has it writes nothing (test_follow_no_write.py).

Canvas sizes change only when the person sets them, so the log says
when one changes and why: canvas_create and canvas_update carry the
sizes, and a page that takes in a different size says so.

Run locally (each session takes its own free port):
    python -m pytest tests/test_launch_canvas_size.py -v --browser chromium
"""

import json
import urllib.request

import pytest

import app as app_module
from conftest import new_server_run

# No module-wide skip: the browser tests skip by themselves without
# Playwright (conftest pw_browser), and the server-only tests at the end
# still run.


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project and preferences the way this module
    found them."""


# Every log line of the test: the pages' own (POST /api/log) and the
# canvas routes'.
EVENTS = []


@pytest.fixture(autouse=True)
def _log_lines(monkeypatch):
    import routes_canvas
    import routes_logs
    EVENTS.clear()
    page_log, canvas_log = routes_logs.log_event, routes_canvas.log_event

    def from_page(action, details=None, *args, **kwargs):
        EVENTS.append(('page', action, dict(details or {})))
        return page_log(action, details, *args, **kwargs)

    def from_server(action, details=None, *args, **kwargs):
        EVENTS.append(('server', action, dict(details or {})))
        return canvas_log(action, details, *args, **kwargs)
    monkeypatch.setattr(routes_logs, 'log_event', from_page)
    monkeypatch.setattr(routes_canvas, 'log_event', from_server)
    yield


PREFS = {'rasterWidth': 3840, 'rasterHeight': 2160, 'processorType': 'brompton',
         'bitDepth': 10, 'frameRate': 30, 'columns': 20, 'rows': 5}
# A real browser (no navigator.webdriver): the launch UI comes up as it does
# for a person. The Preferences live in the browser; the relaunched server
# has none until the page seeds them.
LAUNCH = (
    "Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => false, configurable: true });"
    "try{localStorage.setItem('lrd_quickstart_first_run_done','1');"
    "localStorage.setItem('appPreferences', %s);}catch(e){}"
) % json.dumps(json.dumps(PREFS))
JOIN = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"

SIZES = """() => (window.app.project.canvases || []).map(c => ({
    id: c.id, w: c.raster_width, h: c.raster_height,
    sw: c.show_raster_width, sh: c.show_raster_height}))"""


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _server(url):
    with _opener().open(url + '/api/project', timeout=10) as reply:
        return json.loads(reply.read().decode('utf-8'))


def _server_sizes(url):
    return [{'id': c['id'], 'w': c['raster_width'], 'h': c['raster_height'],
             'sw': c['show_raster_width'], 'sh': c['show_raster_height']}
            for c in _server(url)['canvases']]


def _relaunch(url):
    """What a quit and launch leave: a fresh pristine show, a server with
    no preferences, nobody has had the start page."""
    app_module.server_preferences = {}
    req = urllib.request.Request(url + '/api/project/new', data=b'', method='POST')
    with _opener().open(req, timeout=10) as reply:
        assert reply.status == 200
    new_server_run()


def _context(pw_browser, init):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(init)
    body = json.dumps({'ok': False, 'cancelled': True})
    context.route('**/api/native-dialog/**', lambda route: route.fulfill(
        status=200, content_type='application/json', body=body))
    return context


class _PageLog:
    """The log lines one page sent, read when asked (its id is known once
    it has loaded)."""

    def __init__(self):
        self.page_id = None

    def entries(self):
        return [(action, d) for who, action, d in EVENTS
                if who == 'page' and d.get('page') == self.page_id]

    def actions(self):
        return [action for action, _ in self.entries()]

    def of(self, action):
        return [d for a, d in self.entries() if a == action]


def _open(context, url):
    """A page, its own log lines and its writes."""
    pg = context.new_page()
    log, writes, problems = _PageLog(), [], []

    def on_request(req):
        if req.method != 'GET' and '/api/' in req.url and not req.url.endswith('/api/log'):
            writes.append(f'{req.method} {req.url.split("/api/", 1)[1]}')
    pg.on('request', on_request)
    pg.on('pageerror', lambda e: problems.append(str(e)))
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    log.page_id = pg.evaluate("() => window.app.launchPageId()")
    return pg, log, writes, problems


def _settle(pg, url, ok, timeout_ms=5000):
    waited = 0
    sizes = _server_sizes(url)
    while not ok(sizes) and waited < timeout_ms:
        pg.wait_for_timeout(100)
        waited += 100
        sizes = _server_sizes(url)
    return sizes


FOUR_K = {'w': 3840, 'h': 2160, 'sw': 3840, 'sh': 2160}


def _is_4k(c):
    return {k: c[k] for k in ('w', 'h', 'sw', 'sh')} == FOUR_K


def test_a_relaunch_gives_the_server_the_preference_canvas_size(e2e_server, pw_browser):
    _relaunch(e2e_server)
    context = _context(pw_browser, LAUNCH)
    try:
        pg, logs, writes, problems = _open(context, e2e_server)
        # the server's show takes the Preferences' size, not just the page
        sizes = _settle(pg, e2e_server, lambda s: s and _is_4k(s[0]))
        assert len(sizes) == 1 and _is_4k(sizes[0]), sizes
        assert _is_4k(pg.evaluate(SIZES)[0])
        assert 'follow_write_refused' not in logs.actions(), logs.entries()
        # and says so, once, naming the canvas and both sizes
        synced = logs.of('canvas_size_changed')
        assert len(synced) == 1, logs.entries()
        d = synced[0]
        assert (d.get('id'), d.get('from'), d.get('to'), d.get('reason')) == (
            'c1', '1920x1080', '3840x2160', 'startup_preferences'), d
        # the show is still the launch's pristine one
        assert _server(e2e_server)['is_pristine'] is True
        # and its startup screen holds the Preferences on the server too,
        # not only on the page
        keys = ['processorType', 'bitDepth', 'frameRate', 'powerVoltage', 'powerAmperage', 'panelWatts']
        on_page = pg.evaluate("(keys) => keys.map(k => window.app.project.layers[0][k])", keys)
        assert on_page[:3] == ['brompton', 10, 30], on_page
        pg.wait_for_timeout(500)
        srv_layer = _server(e2e_server)['layers'][0]
        assert [srv_layer.get(k) for k in keys] == on_page, (srv_layer, on_page)
        assert problems == [], problems
    finally:
        context.close()


def test_canvas_1_keeps_its_size_through_add_canvas_and_a_screen_on_canvas_2(e2e_server, pw_browser):
    """The owner's steps: launch, New project, Use Panel, + Add Canvas,
    move Canvas 2, Add Screen. Canvas 1 stays 3840 x 2160 on the page and
    on the server, and Canvas 2 lands beside it, not on top."""
    _relaunch(e2e_server)
    context = _context(pw_browser, LAUNCH)
    try:
        pg, logs, writes, problems = _open(context, e2e_server)
        pg.wait_for_function("() => window.app.startPageOpen()", timeout=15000)
        pg.locator('#start-page-new').click()
        pg.wait_for_function("() => document.getElementById('preset-picker-modal').style.display === 'block'",
                             timeout=10000)
        pg.locator('#preset-picker-add').wait_for(state='visible')
        # the first library panel the catalog lists, picked the user's way
        pg.evaluate("""async () => {
            const app = window.app;
            for (let i = 0; i < 200 && !(app._panelCatalogFlat && app._panelCatalogFlat.length); i++)
                await new Promise(r => setTimeout(r, 50));
            const p = app._panelCatalogFlat.find(x => x.pixels_w === 160 && x.pixels_h === 320 && x.name);
            const search = document.getElementById('panel-catalog-search');
            search.value = p.name;
            search.dispatchEvent(new Event('input', {bubbles: true}));
            let row = null;
            for (let i = 0; i < 100 && !row; i++) {
                await new Promise(r => setTimeout(r, 50));
                row = [...document.querySelectorAll('#panel-catalog-list .panel-catalog-row')]
                    .find(el => el.dataset.mfr === p._mfr && el.dataset.name === p.name) || null;
            }
            row.click();
        }""")
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("() => window.app.project.layers.length === 1"
                             " && window.app.project.layers[0].panelModelName", timeout=10000)
        assert pg.evaluate("() => [window.app.project.layers[0].columns, window.app.project.layers[0].rows]") == [20, 5]
        pg.evaluate("() => window.app.addCanvas()")
        pg.wait_for_function("() => window.app.project.canvases.length === 2", timeout=10000)
        page_sizes = pg.evaluate(SIZES)
        assert _is_4k(page_sizes[0]) and _is_4k(page_sizes[1]), page_sizes
        c2 = next(c for c in _server(e2e_server)['canvases'] if c['id'] == 'c2')
        assert c2['workspace_x'] == 3840, c2   # beside Canvas 1, not on its screen
        pg.evaluate("() => window.app.updateCanvas('c2', {workspace_x: 3900, workspace_y: 0})")
        pg.wait_for_timeout(300)
        # Add Screen, nothing picked: Screen1's panel, on Canvas 2
        pg.evaluate("() => window.app.openPresetPicker()")
        pg.wait_for_selector('#preset-picker-list .preset-picker-row[data-kind="default"]', timeout=5000)
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("() => window.app.project.layers.length === 2", timeout=10000)
        pg.wait_for_timeout(500)
        assert pg.evaluate("() => window.app.project.layers[1].canvas_id") == 'c2'
        for sizes in (pg.evaluate(SIZES), _server_sizes(e2e_server)):
            assert [c['id'] for c in sizes] == ['c1', 'c2'], sizes
            assert all(_is_4k(c) for c in sizes), sizes
        # Canvas 1 again: its Canvas Size fields read 3840 x 2160
        pg.evaluate("() => window.app.selectLayer(window.app.project.layers[0])")
        pg.wait_for_timeout(200)
        assert pg.evaluate("() => window.app.project.active_canvas_id") == 'c1'
        assert pg.evaluate("() => [document.getElementById('toolbar-raster-width').value,"
                           " document.getElementById('toolbar-raster-height').value]") == ['3840', '2160']
        # Show Look sees the same sizes
        pg.locator('.view-tab[data-mode="show-look"]').click()
        pg.wait_for_timeout(200)
        assert pg.evaluate("() => [window.canvasRenderer.rasterWidth, window.canvasRenderer.rasterHeight]") == [3840, 2160]
        assert 'follow_write_refused' not in logs.actions(), logs.entries()
        # the server's log names every canvas's size as it is made
        made = [d for who, a, d in EVENTS if who == 'server' and a == 'canvas_create']
        assert [(d.get('id'), d.get('size'), d.get('show_size')) for d in made] == [
            ('c2', '3840x2160', '3840x2160')], made
        # a move is no size change: no size in its log line
        moves = [d for who, a, d in EVENTS if who == 'server' and a == 'canvas_update']
        assert moves and all('size_from' not in d for d in moves), moves
        assert problems == [], problems
    finally:
        context.close()


def test_a_page_joining_the_launched_show_writes_no_canvas_size(e2e_server, pw_browser):
    """The follow rule stands: a second page on a show that already has
    the Preferences' size finds nothing to send."""
    _relaunch(e2e_server)
    launch = _context(pw_browser, LAUNCH)
    join = None
    try:
        pg, _, _, _ = _open(launch, e2e_server)
        _settle(pg, e2e_server, lambda s: s and _is_4k(s[0]))
        join = _context(pw_browser, JOIN)
        other, logs, writes, problems = _open(join, e2e_server)
        other.wait_for_timeout(800)
        assert not any(w.startswith('POST project') for w in writes), writes
        assert 'follow_write_refused' not in logs.actions(), logs.entries()
        assert 'canvas_size_changed' not in logs.actions(), logs.entries()
        assert _is_4k(other.evaluate(SIZES)[0])
        assert problems == [], problems
    finally:
        if join:
            join.close()
        launch.close()


def test_a_new_browser_joining_a_show_shows_its_canvas_size_not_the_preferences(e2e_server, pw_browser):
    """A browser that has never run the app (a tablet joining the show)
    shows the show's own Canvas Size, never its Preferences', and sends
    none: the startup sync is for the launch's pristine show only."""
    _relaunch(e2e_server)
    # a show someone is working on: not the launch's pristine one
    req = urllib.request.Request(e2e_server + '/api/project', method='POST',
                                 data=json.dumps({'name': 'Working Show'}).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with _opener().open(req, timeout=10) as reply:
        assert reply.status == 200
    assert _server(e2e_server)['is_pristine'] is False
    assert [(c['w'], c['h']) for c in _server_sizes(e2e_server)] == [(1920, 1080)]
    app_module.server_preferences = dict(PREFS)
    context = _context(pw_browser, JOIN)
    try:
        pg, logs, writes, problems = _open(context, e2e_server)
        pg.wait_for_timeout(500)
        sizes = pg.evaluate(SIZES)
        assert [(c['w'], c['h'], c['sw'], c['sh']) for c in sizes] == [(1920, 1080, 1920, 1080)], sizes
        assert pg.evaluate("() => [document.getElementById('toolbar-raster-width').value,"
                           " document.getElementById('toolbar-raster-height').value]") == ['1920', '1080']
        assert [(c['w'], c['h']) for c in _server_sizes(e2e_server)] == [(1920, 1080)]
        assert 'canvas_size_changed' not in logs.actions(), logs.entries()
        assert problems == [], problems
    finally:
        context.close()




def test_the_startup_screen_takes_the_preferences_on_the_server_with_the_default_grid(e2e_server, pw_browser):
    """The startup screen's own Preferences (processor, bit depth, frame
    rate, power) reach the server after a relaunch, also when the grid
    preference is the startup screen's own 8 x 5 and nothing else about
    its size changes."""
    _relaunch(e2e_server)
    prefs = {k: v for k, v in PREFS.items() if k not in ('columns', 'rows')}
    init = LAUNCH.replace(json.dumps(json.dumps(PREFS)), json.dumps(json.dumps(prefs)))
    assert init != LAUNCH
    context = _context(pw_browser, init)
    try:
        pg, logs, writes, problems = _open(context, e2e_server)
        _settle(pg, e2e_server, lambda s: s and _is_4k(s[0]))
        pg.wait_for_timeout(800)
        keys = ['columns', 'rows', 'processorType', 'bitDepth', 'frameRate',
                'powerVoltage', 'powerAmperage', 'panelWatts']
        on_page = pg.evaluate("(keys) => keys.map(k => window.app.project.layers[0][k])", keys)
        assert on_page[:5] == [8, 5, 'brompton', 10, 30], on_page
        srv_layer = _server(e2e_server)['layers'][0]
        assert [srv_layer.get(k) for k in keys] == on_page, (srv_layer, on_page, logs.actions())
        assert problems == [], problems
    finally:
        context.close()

def _put_project(url, project, reason=None):
    path = '/api/project' + (f'?reason={reason}' if reason else '')
    req = urllib.request.Request(url + path, method='PUT',
                                 data=json.dumps(project).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with _opener().open(req, timeout=10) as reply:
        assert reply.status == 200


def _call(url, method, path, body):
    req = urllib.request.Request(url + path, method=method,
                                 data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with _opener().open(req, timeout=10) as reply:
        assert reply.status == 200


def test_a_show_opened_while_the_launch_loads_never_takes_the_preferences(e2e_server, pw_browser):
    """The socket's first copy can land before the load's own read answers.
    Taken in, the pristine startup show it carried left the startup sync
    owing; if another page opened a file meanwhile, the load brought that
    show, and the owed sync put the Preferences' Canvas Size on it."""
    _relaunch(e2e_server)
    context = _context(pw_browser, LAUNCH)
    held = []

    def hold_first_read(route):
        if route.request.method == 'GET' and not held:
            held.append(route)       # answered below, once the show is opened
        else:
            route.continue_()
    context.route('**/api/project', hold_first_read)
    try:
        pg = context.new_page()
        writes = []
        pg.on('request', lambda r: writes.append(f'{r.method} {r.url.split("/api/", 1)[1]}')
              if r.method != 'GET' and '/api/project' in r.url else None)
        pg.goto(e2e_server, wait_until='domcontentloaded')
        # the socket's copy of the pristine show has been taken in and owes the sync
        pg.wait_for_function("() => !!(window.app && window.app._owedStartupSync)", timeout=20000)
        assert held, 'the load read was not held'
        # another page opens a show with a 1920 x 1080 canvas
        opened = _server(e2e_server)
        opened['name'] = 'Opened Show'
        opened['is_pristine'] = False
        _put_project(e2e_server, opened, reason='open')
        assert [(c['w'], c['h']) for c in _server_sizes(e2e_server)] == [(1920, 1080)]
        held[0].continue_()
        pg.wait_for_function("() => window.app._initialLoadComplete === true", timeout=20000)
        pg.wait_for_timeout(1000)
        srv = _server(e2e_server)
        assert srv['name'] == 'Opened Show'
        assert [(c['w'], c['h'], c['sw'], c['sh']) for c in _server_sizes(e2e_server)] == [
            (1920, 1080, 1920, 1080)], srv['canvases']
        assert not [w for w in writes if w.startswith('POST project')], writes
    finally:
        context.close()


def test_a_reconnect_takes_the_servers_canvas_sizes_and_writes_nothing(e2e_server, pw_browser):
    """The server's word is the truth after a disconnect (2026-11-10). The
    page used to keep the size its active canvas had and wrote it onto
    whichever canvas the server's copy had active: Canvas 2 took Canvas 1's
    size on this page."""
    _relaunch(e2e_server)
    show = _server(e2e_server)
    show['name'] = 'Two Canvases'
    show['is_pristine'] = False
    c1 = show['canvases'][0]
    c1.update(raster_width=3840, raster_height=2160, show_raster_width=3840, show_raster_height=2160)
    c2 = dict(c1, id='c2', name='Canvas 2', workspace_x=3840,
              raster_width=1920, raster_height=1080, show_raster_width=1920, show_raster_height=1080)
    show['canvases'] = [c1, c2]
    show['active_canvas_id'] = 'c1'
    _put_project(e2e_server, show, reason='open')
    context = _context(pw_browser, JOIN)
    try:
        pg, logs, writes, problems = _open(context, e2e_server)
        assert pg.evaluate("() => window.app.project.active_canvas_id") == 'c1'
        pg.evaluate("() => window.app.socket.disconnect()")
        pg.wait_for_function("() => !window.app.socket.connected", timeout=5000)
        # meanwhile another page gives Canvas 1 a new size and works on Canvas 2
        _call(e2e_server, 'PUT', '/api/canvas/c1', {'raster_width': 2560, 'raster_height': 1440,
                                                     'show_raster_width': 2560, 'show_raster_height': 1440})
        _call(e2e_server, 'POST', '/api/project', {'active_canvas_id': 'c2'})
        before = list(writes)
        pg.evaluate("() => window.app.socket.connect()")
        # the server's copy arrives with Canvas 2 active; the page's own
        # selection (Screen1, on Canvas 1) then brings Canvas 1 back
        pg.wait_for_function("() => window.app.project.canvases[0].raster_width === 2560", timeout=10000)
        pg.wait_for_timeout(800)
        sizes = {c['id']: (c['w'], c['h'], c['sw'], c['sh']) for c in pg.evaluate(SIZES)}
        assert sizes == {'c1': (2560, 1440, 2560, 1440), 'c2': (1920, 1080, 1920, 1080)}, sizes
        # the size fields read the active canvas's size
        active = pg.evaluate("() => window.app.project.active_canvas_id")
        want = [str(sizes[active][0]), str(sizes[active][1])]
        assert pg.evaluate("() => [document.getElementById('toolbar-raster-width').value,"
                           " document.getElementById('toolbar-raster-height').value]") == want
        assert {c['id']: (c['w'], c['h']) for c in _server_sizes(e2e_server)} == {
            'c1': (2560, 1440), 'c2': (1920, 1080)}
        # the port map's reads go by POST; nothing else may
        new = [w for w in writes[len(before):]
               if not w.startswith(('POST port-assignments/resolve', 'POST port-assignments/link-check'))]
        assert new == [], new
        took = [(d.get('id'), d.get('from'), d.get('to'), d.get('reason')) for d in logs.of('canvas_size_changed')]
        assert took == [('c1', '3840x2160', '2560x1440', 'reconnect')], took
        assert problems == [], problems
    finally:
        context.close()


# ── The server's log lines, without a browser ─────────────────────────────

def _server_log(monkeypatch):
    """Every log line the canvas and project routes write, as (action, details)."""
    import routes_canvas
    lines = []
    real = app_module.log_event

    def keep(action, details=None, *args, **kwargs):
        lines.append((action, dict(details or {})))
        return real(action, details, *args, **kwargs)
    monkeypatch.setattr(app_module, 'log_event', keep)
    monkeypatch.setattr(routes_canvas, 'log_event', keep)
    return lines


def test_canvas_routes_log_every_size_change(client, monkeypatch):
    lines = _server_log(monkeypatch)
    client.post('/api/canvas', json={'raster_width': 3840, 'raster_height': 2160,
                                     'show_raster_width': 3840, 'show_raster_height': 2160})
    made = [d for a, d in lines if a == 'canvas_create']
    assert [(d['id'], d['size'], d['show_size']) for d in made] == [('c2', '3840x2160', '3840x2160')]
    # a move: no size in the line
    client.put('/api/canvas/c2', json={'workspace_x': 100})
    # a typed size: the old and the new
    client.put('/api/canvas/c2', json={'raster_width': 1920, 'raster_height': 1080})
    updates = [d for a, d in lines if a == 'canvas_update']
    assert 'size_from' not in updates[0], updates
    assert (updates[1]['size_from'], updates[1]['size_to']) == ('3840x2160', '1920x1080'), updates
    assert (updates[1]['show_size_from'], updates[1]['show_size_to']) == ('3840x2160', '3840x2160'), updates


def test_project_routes_name_the_canvas_whose_size_they_change(client, monkeypatch):
    lines = _server_log(monkeypatch)
    # the startup sync: root sizes land on the active canvas
    client.post('/api/project', json={'raster_width': 3840, 'raster_height': 2160,
                                      'show_raster_width': 3840, 'show_raster_height': 2160,
                                      'keep_pristine': True})
    # nothing to change: no line
    client.post('/api/project', json={'raster_width': 3840, 'keep_pristine': True})
    # an undo putting the old size back
    proj = client.get('/api/project').get_json()
    proj['canvases'][0]['raster_width'] = 1920
    proj['canvases'][0]['raster_height'] = 1080
    client.put('/api/project?reason=undo', json=proj)
    # a file open, which says nothing: a restore
    proj['canvases'][0]['raster_width'] = 2560
    proj['canvases'][0]['raster_height'] = 1440
    client.put('/api/project', json=proj)
    changed = [d for a, d in lines if a == 'canvas_size_changed']
    assert [(d['id'], d['from'], d['to'], d['reason']) for d in changed] == [
        ('c1', '1920x1080', '3840x2160', 'project_save_pristine_sync'),
        ('c1', '3840x2160', '1920x1080', 'project_undo'),
        ('c1', '1920x1080', '2560x1440', 'project_restore'),
    ], changed
