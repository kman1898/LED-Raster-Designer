"""A following page shows every field another page changes (2026-11-10).

Owner's live-service ruling: every change shows on every device. A page
taking in another page's save of a screen (its layer_updated) kept its OWN
value for every field on the client-side-props list (app-core
extractClientSideProps) wherever it already held one: the flow pattern,
the processor, the frame rate, a custom data path, most power fields. That
list dates from when the server dropped those fields on every PUT, so the
page re-stamped its copy over each echo; the server has stored every one
of them since (test_layer_appearance_persistence), and the re-stamp now
only hid another page's change. A tablet showed a stale data map, power
map or processor until it reloaded.

Now a follow takes every field the server sends, except a field this page
is editing: a Screen Info field being typed in keeps its typing, and a
field changed here and not yet saved keeps its value (the rule an echo of
this page's own save already follows, app-core _keepUnsavedEdits).

The server also keeps a mirror screen's data map its source's
(port_assignment.copy_mirror_maps): on every save of the source, on a save
of the mirror itself, and when a show is loaded, restored or saved whole.
A mirror stored out of date (a script, an old file, a page that died
mid-save) no longer waits for some page to edit again, which a following
page never does (test_follow_no_write.py).

Run locally:
    python -m pytest tests/test_follow_fields.py -v --browser chromium
"""

import json
import time
import urllib.request
from urllib.parse import urlparse

import pytest

import app as app_module
import port_assignment

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared project the way this module found it."""


FIELDS = list(port_assignment.MIRROR_DATA_FIELDS)


# ── the server keeps a mirror's map its source's ──────────────────────────

def _two_screens(client):
    client.post('/api/project/new')
    proj = client.get('/api/project').get_json()
    proj['layers'] = []
    proj['groups'] = []
    client.put('/api/project', json=proj)
    ids = []
    for name, x in (('Source', 0), ('Copy', 2000)):
        layer = client.post('/api/layer/add', json={
            'name': name, 'columns': 6, 'rows': 3, 'cabinet_width': 128,
            'cabinet_height': 128, 'offset_x': x, 'offset_y': 0}).get_json()
        client.put(f"/api/layer/{layer['id']}", json={
            'processorType': 'novastar-armor', 'bitDepth': 8, 'frameRate': 60,
            'flowPattern': 'tl-h', 'portMappingMode': 'organized',
            'portNumberOrder': 'across', 'lowLatency': False})
        ids.append(layer['id'])
    r = client.put(f'/api/layer/{ids[1]}', json={'dataMirrorOf': ids[0]})
    assert r.status_code == 200, r.get_json()
    return ids


def _layer(client, layer_id):
    return next(l for l in client.get('/api/project').get_json()['layers']
                if l['id'] == layer_id)


def _map(layer):
    return {k: layer.get(k) for k in FIELDS}


def _mirror_echoes(sock, layer_id):
    return [r['args'][0] for r in sock.get_received()
            if r['name'] == 'layer_updated' and r['args'][0].get('id') == layer_id]


PATH = {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}, {'row': 0, 'col': 2}]}


def test_a_source_s_save_copies_its_map_onto_the_mirror_and_tells_the_pages(client):
    src, copy = _two_screens(client)
    sock = app_module.socketio.test_client(app_module.app)
    try:
        sock.get_received()
        r = client.put(f'/api/layer/{src}', json={
            'flowPattern': 'br-v', 'frameRate': 30, 'customPortPaths': PATH,
            'customPortIndex': 2})
        assert r.status_code == 200
        stored = _layer(client, copy)
        assert _map(stored) == _map(_layer(client, src))
        assert stored['flowPattern'] == 'br-v' and stored['frameRate'] == 30
        assert stored['customPortPaths'] == PATH
        # the copy's own news goes to every page, from no page
        got = _mirror_echoes(sock, copy)
        assert got and got[-1]['flowPattern'] == 'br-v', got
        assert '_echo' not in got[-1]
        # a copy of the source's value, never the same object
        assert app_module.current_project['layers'][1]['customPortPaths'] \
            is not app_module.current_project['layers'][0]['customPortPaths']
    finally:
        sock.disconnect()


def test_a_field_the_source_lacks_is_blank_on_the_mirror(client):
    src, copy = _two_screens(client)
    client.put(f'/api/layer/{copy}', json={'customPortPaths': PATH})
    layer = next(l for l in app_module.current_project['layers'] if l['id'] == src)
    layer.pop('customPortPaths', None)
    client.put(f'/api/layer/{src}', json={'name': 'Source'})
    assert _layer(client, copy).get('customPortPaths') is None


def test_a_save_of_the_mirror_itself_keeps_the_source_s_map(client):
    """A page holding an older copy of the mirror saves it whole (a rename):
    the map it carries is put back to the source's."""
    src, copy = _two_screens(client)
    client.put(f'/api/layer/{src}', json={'flowPattern': 'bl-h'})
    stale = _layer(client, copy)
    stale.update(name='Copy Renamed', flowPattern='tl-h', frameRate=24)
    r = client.put(f'/api/layer/{copy}', json=stale)
    assert r.status_code == 200
    got = r.get_json()
    assert got['name'] == 'Copy Renamed'
    assert got['flowPattern'] == 'bl-h' and got['frameRate'] == 60
    assert _map(_layer(client, copy)) == _map(_layer(client, src))


def test_a_show_loaded_with_an_out_of_date_mirror_is_repaired(client):
    src, copy = _two_screens(client)
    proj = client.get('/api/project').get_json()
    for l in proj['layers']:
        if l['id'] == src:
            l.update(flowPattern='br-h', frameRate=50, customPortPaths=PATH)
    sock = app_module.socketio.test_client(app_module.app)
    try:
        sock.get_received()
        r = client.put('/api/project?reason=open', json=proj)
        assert r.status_code == 200
        # the answer, the store and the message every page takes in
        answered = next(l for l in r.get_json()['layers'] if l['id'] == copy)
        assert answered['flowPattern'] == 'br-h' and answered['customPortPaths'] == PATH
        assert _map(_layer(client, copy)) == _map(_layer(client, src))
        sent = [x['args'][0] for x in sock.get_received() if x['name'] == 'project_updated']
        assert sent, 'no page was told'
        assert next(l for l in sent[-1]['layers'] if l['id'] == copy)['frameRate'] == 50
    finally:
        sock.disconnect()


def test_a_whole_layers_save_with_an_out_of_date_mirror_is_repaired(client):
    src, copy = _two_screens(client)
    proj = client.get('/api/project').get_json()
    for l in proj['layers']:
        if l['id'] == src:
            l['flowPattern'] = 'tr-v'
    sock = app_module.socketio.test_client(app_module.app)
    try:
        sock.get_received()
        client.post('/api/project', json={'layers': proj['layers']})
        assert _layer(client, copy)['flowPattern'] == 'tr-v'
        got = _mirror_echoes(sock, copy)
        assert got and got[-1]['flowPattern'] == 'tr-v', got
    finally:
        sock.disconnect()


def test_a_mirror_of_nothing_or_of_a_mirror_is_left_alone(client):
    src, copy = _two_screens(client)
    # its source deleted: the stale id copies nothing
    proj = client.get('/api/project').get_json()
    before = _map(_layer(client, copy))
    proj['layers'] = [l for l in proj['layers'] if l['id'] != src]
    client.put('/api/project', json=proj)
    assert _map(_layer(client, copy)) == before
    assert port_assignment.copy_mirror_maps(app_module.current_project) == []


def test_copied_fields_are_the_client_s_list():
    """The server copies exactly what the client's _syncMirrorScreens does
    (app-mirror-screens.js MIRROR_DATA_FIELDS)."""
    from pathlib import Path
    import re
    js = (Path(__file__).resolve().parents[1] / 'src' / 'static' / 'js'
          / 'app-mirror-screens.js').read_text(encoding='utf-8')
    block = js.split('export const MIRROR_DATA_FIELDS = [')[1].split('];')[0]
    assert re.findall(r"'([A-Za-z]+)'", block) == FIELDS


# ── in the browser: two pages on one server ───────────────────────────────

QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
UNAVAILABLE = json.dumps({'ok': False, 'cancelled': True})
NOT_WRITES = {'/api/log', '/api/port-assignments/resolve',
              '/api/port-assignments/link-check'}


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _call(url, method, path, body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    with _opener().open(req, timeout=10) as reply:
        assert reply.status in (200, 201)
        return json.loads(reply.read().decode('utf-8'))


def _server(url):
    return _call(url, 'GET', '/api/project')


def _server_layer(url, layer_id):
    return next(l for l in _server(url)['layers'] if l['id'] == layer_id)


def _settled(url, want, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = _server(url)
        if want(got):
            return got
        time.sleep(0.2)
    raise AssertionError('the server never got there')


def _seed(url, mirror=False):
    """Screen1 and Screen2 alike, a show of its own; Screen2 mirrors
    Screen1 when asked."""
    _call(url, 'POST', '/api/project/new')
    proj = _server(url)
    proj['layers'] = []
    proj['groups'] = []
    proj['processors'] = []
    proj['distros'] = []
    for k in ('port_assignments', 'fiberCables', 'snakes'):
        proj.pop(k, None)
    _call(url, 'PUT', '/api/project', proj)
    ids = {}
    for name, x in (('Screen1', 0), ('Screen2', 1500)):
        layer = _call(url, 'POST', '/api/layer/add', {
            'name': name, 'columns': 10, 'rows': 5, 'cabinet_width': 128,
            'cabinet_height': 128, 'offset_x': x, 'offset_y': 0})
        _call(url, 'PUT', f"/api/layer/{layer['id']}", {
            'processorType': 'novastar-armor', 'bitDepth': 8, 'frameRate': 60,
            'flowPattern': 'tl-h', 'panelWatts': 200, 'portMappingMode': 'organized',
            'portNumberOrder': 'across', 'lowLatency': False,
            'customPortPaths': {}, 'customPortIndex': 1, 'customPortOverrides': []})
        ids[name] = layer['id']
    if mirror:
        _call(url, 'PUT', f"/api/layer/{ids['Screen2']}", {'dataMirrorOf': ids['Screen1']})
    _call(url, 'POST', '/api/project', {'name': 'Follow Show'})
    return ids


def _context(pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(QUIET)
    for name in ('save-file', 'open-file', 'select-directory'):
        context.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json', body=UNAVAILABLE))
    return context


def _watch(pg):
    problems = []
    pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))

    def response(r):
        if '/api/' in r.url and r.status >= 400 and '/api/native-dialog/' not in r.url \
                and '/api/panel-catalog/refresh' not in r.url:
            problems.append(f'{r.status} {r.url}')
    pg.on('response', response)
    return problems


def _record_writes(target):
    writes = []

    def request(req):
        if req.method in ('GET', 'HEAD', 'OPTIONS'):
            return
        at = urlparse(req.url)
        if not at.path.startswith('/api/') or at.path in NOT_WRITES:
            return
        writes.append(f'{req.method} {at.path}' + (f'?{at.query}' if at.query else ''))
    target.on('request', request)
    return writes


def _open(context, url, tab='data-flow'):
    pg = context.new_page()
    problems = _watch(pg)
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.wait_for_timeout(800)
    _tab(pg, tab)
    return pg, problems


def _tab(pg, tab):
    pg.locator(f'#view-tabs .view-tab[data-mode="{tab}"]').click()
    pg.wait_for_timeout(300)


def _select(pg, layer_id):
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))",
                layer_id)
    pg.wait_for_timeout(200)


def _held(pg, layer_id, keys):
    return pg.evaluate("([id, keys]) => { const l = window.app.project.layers.find(x => x.id === id);"
                       " return Object.fromEntries(keys.map(k => [k, l[k] === undefined ? null : l[k]])); }",
                       [layer_id, keys])


def _follows(pg, url, layer_id, keys, timeout=10.0):
    """`pg` comes to hold the server's value of every key on the screen."""
    deadline = time.time() + timeout
    want = got = None
    while time.time() < deadline:
        srv = _server_layer(url, layer_id)
        want = {k: srv.get(k) for k in keys}
        got = _held(pg, layer_id, keys)
        if got == want:
            return want
        time.sleep(0.2)
    raise AssertionError(f'the page kept its own values: {got} != the server\'s {want}')


# Page A's edits, made the way a person makes them.
PATTERN_JS = """(pattern) => document.querySelector(
    `.flow-pattern-btn:not(.power-flow-pattern-btn)[data-pattern="${pattern}"]`).click()"""
CUSTOM_PATH_JS = """() => {
    const app = window.app;
    const l = app.currentLayer;
    l.customPortPaths = {'1': [{row: 0, col: 0}, {row: 0, col: 1}, {row: 0, col: 2}]};
    l.customPortIndex = 2;
    app.updateLayer(true, 'Custom Path');
}"""

FOLLOWED = ['flowPattern', 'frameRate', 'processorType', 'customPortPaths',
            'customPortIndex', 'panelWatts']


def _a_changes_screen1(a, ids, url):
    _select(a, ids['Screen1'])
    a.evaluate(PATTERN_JS, 'br-v')
    a.select_option('#frame-rate', '30')
    a.select_option('#processor-type', 'novastar-coex-1g')
    a.evaluate(CUSTOM_PATH_JS)
    _tab(a, 'power')
    a.locator('#power-panel-watts').fill('250')
    a.locator('#power-panel-watts').press('Enter')
    _tab(a, 'data-flow')
    return _settled(url, lambda p: (lambda l: l.get('flowPattern') == 'br-v'
                                    and str(l.get('frameRate')) == '30'
                                    and l.get('processorType') == 'novastar-coex-1g'
                                    and (l.get('customPortPaths') or {}).get('1')
                                    and str(l.get('panelWatts')) == '250')(
        next(x for x in p['layers'] if x['id'] == ids['Screen1'])))


def test_a_following_page_shows_every_field_another_page_changes(e2e_server, pw_browser):
    ids = _seed(e2e_server)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, pa = _open(ctx_a, e2e_server)
        b, pb = _open(ctx_b, e2e_server)
        _select(b, ids['Screen1'])
        writes_b = _record_writes(ctx_b)
        _a_changes_screen1(a, ids, e2e_server)
        got = _follows(b, e2e_server, ids['Screen1'], FOLLOWED)
        assert got['flowPattern'] == 'br-v' and got['processorType'] == 'novastar-coex-1g'
        # ... and Screen Info shows them
        b.wait_for_function("() => document.getElementById('processor-type').value === 'novastar-coex-1g'",
                            timeout=5000)
        assert b.locator('#frame-rate').input_value() == '30'
        assert b.evaluate("() => document.querySelector("
                          "'.flow-pattern-btn:not(.power-flow-pattern-btn).active').dataset.pattern") == 'br-v'
        assert b.locator('#power-panel-watts').input_value() == '250'
        b.wait_for_timeout(1200)
        assert writes_b == [], writes_b
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()


def test_typing_on_the_following_page_is_kept(e2e_server, pw_browser):
    """B is typing a panel wattage, not yet entered, when A changes the
    same screen: the field keeps the typing, everything else follows, and
    Enter then saves what B typed."""
    ids = _seed(e2e_server)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, pa = _open(ctx_a, e2e_server)
        b, pb = _open(ctx_b, e2e_server, tab='power')
        _select(b, ids['Screen1'])
        field = b.locator('#power-panel-watts')
        field.click()
        field.fill('333')
        writes_b = _record_writes(ctx_b)
        _a_changes_screen1(a, ids, e2e_server)
        _follows(b, e2e_server, ids['Screen1'],
                 ['flowPattern', 'frameRate', 'processorType', 'customPortPaths', 'panelWatts'])
        assert field.input_value() == '333'
        assert b.evaluate("() => document.activeElement && document.activeElement.id") == 'power-panel-watts'
        assert writes_b == [], writes_b
        field.press('Enter')
        _settled(e2e_server, lambda p: str(next(l for l in p['layers']
                                               if l['id'] == ids['Screen1']).get('panelWatts')) == '333')
        # B's save carries A's other changes, never its own older copy
        srv = _server_layer(e2e_server, ids['Screen1'])
        assert srv['flowPattern'] == 'br-v' and srv['processorType'] == 'novastar-coex-1g'
        a.wait_for_function(f"() => String(window.app.project.layers.find(l => l.id === {ids['Screen1']})"
                            ".panelWatts) === '333'", timeout=10000)
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()


def test_the_server_repairs_a_mirror_and_the_pages_show_it_writing_nothing(e2e_server, pw_browser):
    """A mirror stored behind its source (a script's save, an old file):
    the server copies the source's map onto it, on the load and on a save
    of the source, and both pages show the copy without writing it."""
    ids = _seed(e2e_server, mirror=True)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, pa = _open(ctx_a, e2e_server)
        b, pb = _open(ctx_b, e2e_server)
        writes_a, writes_b = _record_writes(ctx_a), _record_writes(ctx_b)
        # an old file with the mirror behind its source, loaded by a script
        proj = _server(e2e_server)
        for l in proj['layers']:
            if l['id'] == ids['Screen1']:
                l.update(flowPattern='br-h', frameRate=50, customPortPaths=PATH, customPortIndex=2)
        _call(e2e_server, 'PUT', '/api/project?reason=open', proj)
        srv = _server_layer(e2e_server, ids['Screen2'])
        assert srv['flowPattern'] == 'br-h' and srv['frameRate'] == 50
        assert srv['customPortPaths'] == PATH
        for pg in (a, b):
            _follows(pg, e2e_server, ids['Screen2'], FIELDS)
        # the source saved by a script: the server copies it
        _call(e2e_server, 'PUT', f"/api/layer/{ids['Screen1']}", {'flowPattern': 'tr-v'})
        assert _server_layer(e2e_server, ids['Screen2'])['flowPattern'] == 'tr-v'
        for pg in (a, b):
            _follows(pg, e2e_server, ids['Screen2'], FIELDS)
        b.wait_for_timeout(1500)
        assert writes_a == [] and writes_b == [], writes_a + writes_b
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()


def test_a_page_changing_a_source_shows_the_mirror_the_server_wrote(e2e_server, pw_browser):
    """Page A changes the mirror's source; the server writes the copy, A
    and B both show it, and B writes nothing."""
    ids = _seed(e2e_server, mirror=True)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, pa = _open(ctx_a, e2e_server)
        b, pb = _open(ctx_b, e2e_server)
        writes_b = _record_writes(ctx_b)
        _select(a, ids['Screen1'])
        a.evaluate(PATTERN_JS, 'bl-v')
        _settled(e2e_server, lambda p: next(l for l in p['layers'] if l['id'] == ids['Screen2'])
                 .get('flowPattern') == 'bl-v')
        for pg in (a, b):
            _follows(pg, e2e_server, ids['Screen2'], FIELDS)
        b.wait_for_timeout(1200)
        assert writes_b == [], writes_b
        assert 'Changes From Another Page' not in a.evaluate("() => window.app.history.map(h => h.action)")
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()
