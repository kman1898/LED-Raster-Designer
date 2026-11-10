"""Only the page that makes a change writes it (2026-11-10).

The running app is a live service: other tabs and devices follow along.
A page that is only FOLLOWING another page's change, or joining the show
as it stands, recomputes what it shows and writes nothing back: no mirror
copy, no port repair, no preference stamp, no raster, no footer lift. A
write from a follower comes back to the page that acted as another page's
edit, so its undo grew a step nobody made (CI on 1b16163f: a second page
ran the mirror copy as it followed a restore and PUT the mirror screen),
and two devices would bounce writes between each other.

Derived state that must be stored is written by the page that acted, as
part of its own change: a mirror's map is copied by the page that changed
its source.

Run locally:
    python -m pytest tests/test_follow_no_write.py -v --browser chromium
"""

import json
import time
import urllib.request
from urllib.parse import urlparse

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
UNAVAILABLE = json.dumps({'ok': False, 'cancelled': True})
FOREIGN = 'Changes From Another Page'
# Requests that change nothing on the server: the page's log and the
# port map's reads.
NOT_WRITES = {'/api/log', '/api/port-assignments/resolve',
              '/api/port-assignments/link-check'}
MIRROR_FIELDS = ['flowPattern', 'portMappingMode', 'portNumberOrder',
                 'processorType', 'bitDepth', 'frameRate', 'lowLatency']


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


def _seed(url):
    """Screen1 and Screen2 alike, a third screen, and a UHD Jr with box
    A-B and a second box set to Mirror (test_mirror_box_drop's rig)."""
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
    for name, x, y in (('Screen1', 0, 0), ('Screen2', 1500, 0), ('Other', 0, 900)):
        layer = _call(url, 'POST', '/api/layer/add', {
            'name': name, 'columns': 10, 'rows': 5, 'cabinet_width': 128,
            'cabinet_height': 128, 'offset_x': x, 'offset_y': y})
        _call(url, 'PUT', f"/api/layer/{layer['id']}",
              {'processorType': 'novastar-armor', 'bitDepth': 8, 'frameRate': 60})
        ids[name] = layer['id']
    st = _call(url, 'POST', '/api/processors', {'deviceId': 'novastar-novapro-uhd-jr'})
    proc = st['resolved'][-1]
    pid, cid = proc['id'], proc['slots'][0]['card']['id']
    _call(url, 'POST', f'/api/processors/{pid}/cards/{cid}/cvts',
          {'deviceId': 'novastar-cvt4k-s'})
    _call(url, 'POST', f'/api/processors/{pid}/cards/{cid}/cvts',
          {'deviceId': 'novastar-cvt4k-s', 'copyRole': 'mirror'})
    _call(url, 'POST', '/api/project', {'name': 'Mirror Show'})
    ids.update(pid=pid, cid=cid)
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
    """Every request `target` (a page or a context) sends that could change
    the server: anything but a read, the page's log and the port map's
    read-only resolve."""
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


def _open(context, url):
    pg = context.new_page()
    problems = _watch(pg)
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.wait_for_timeout(800)
    pg.locator('#view-tabs .view-tab[data-mode="data-flow"]').click()
    pg.wait_for_timeout(300)
    return pg, problems


def _quiet(pg, ms=1500):
    """Let every message, read and write in flight land."""
    pg.wait_for_timeout(ms)


def _settled(url, want, timeout=10.0):
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = _server(url)
        if want(got):
            return got
        time.sleep(0.2)
    raise AssertionError('the server never got there')


def _actions(pg):
    return pg.evaluate("() => window.app.history.map(h => h.action)")


# The box drop the tray's drag makes (test_mirror_box_drop DROP_JS).
DROP_JS = """async ([cid, nth, layerId]) => {
    const app = window.app;
    const box = app._dockFindCard(cid).card.cvts[nth];
    const nums = box.portNumbers || [];
    const payload = {type: 'box', cardId: cid, boxId: box.id,
        first: Math.min(...nums), last: Math.max(...nums),
        title: box.displayTitle, beyondTrunks: !!box.beyondTrunks};
    const target = app._dockDataScreenTarget({payload}, String(layerId), null);
    const before = app.history.length;
    await app._dockPerformDrop(payload, target);
    await new Promise(r => setTimeout(r, 400));
    await app.refreshPortAssignment();
    return {pill: target.pill || null, changed: app.history.length !== before};
}"""

# A flow pattern picked in Screen Info for one screen, as a person does.
PATTERN_JS = """async ([layerId, pattern]) => {
    const app = window.app;
    app.selectLayer(app.project.layers.find(l => l.id === layerId));
    document.querySelector(`.flow-pattern-btn[data-pattern="${pattern}"]`).click();
    await new Promise(r => setTimeout(r, 300));
}"""

# File > Open of the show the page holds (renamed), as a file read does.
OPEN_JS = """async (name) => {
    const app = window.app;
    const file = JSON.parse(app.serializeProjectForFile(JSON.parse(JSON.stringify(app.project))));
    file.name = name;
    await app._openProjectData(file, { source: 'file' });
}"""


# A field a screen does not hold reads as its default (the page fills it).
MIRROR_DEFAULTS = {'portMappingMode': 'organized', 'portNumberOrder': 'across',
                   'lowLatency': False}


def _mirror_settings(layer):
    return {k: layer.get(k) if layer.get(k) is not None else MIRROR_DEFAULTS.get(k)
            for k in MIRROR_FIELDS}


def _make_mirror(a, ids, url):
    """Page A drops box A-B on Screen1 and the Mirror box on Screen2."""
    assert a.evaluate(DROP_JS, [ids['cid'], 0, ids['Screen1']])['changed']
    out = a.evaluate(DROP_JS, [ids['cid'], 1, ids['Screen2']])
    assert out['pill'] == {'ok': True, 'text': 'Copy of Screen1'}, out
    assert out['changed'], out
    _settled(url, lambda p: next(l for l in p['layers'] if l['id'] == ids['Screen2'])
             .get('dataMirrorOf') in (ids['Screen1'], str(ids['Screen1'])))


# The whole show put back from the server's own copy by a script, as the
# mirror tests' rig does between cases (test_mirror_box_drop FIELDS_JS):
# an unmarked PUT /api/project, which every other page takes as a restore.
RESTORE_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const proj = await j('GET', '/api/project');
    await j('PUT', '/api/project', proj);
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.currentLayer = app.project.layers[0];
    app.selectedLayerIds = new Set([app.project.layers[0].id]);
    await app.refreshProcessors();
    app.renderLayers();
    await app.refreshPortAssignment();
    app.resetHistory('Settings Seed');
}"""


def test_a_following_page_writes_nothing_back(e2e_server, pw_browser):
    """Page A makes a mirror; the show is put back whole (the CI case);
    A opens a show, edits the mirror's source, adds a screen and undoes.
    Page B follows every one of them and sends no write, so A's history
    holds A's own steps only, and the mirror's map on the server is the
    one A's own edit wrote."""
    ids = _seed(e2e_server)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, pa = _open(ctx_a, e2e_server)
        b, pb = _open(ctx_b, e2e_server)
        writes_b = _record_writes(b)
        _make_mirror(a, ids, e2e_server)
        _quiet(a)
        # the CI case: B, following the restore, selected Screen1 and
        # copied it onto the mirror, and sent the copy
        a.evaluate(RESTORE_JS)
        _quiet(a, 2000)
        assert writes_b == [], writes_b
        assert _actions(a) == ['Settings Seed'], _actions(a)
        # a show opened on A: B lands on it as a load does
        a.evaluate(OPEN_JS, 'Mirror Show Opened')
        _settled(e2e_server, lambda p: p['name'] == 'Mirror Show Opened')
        b.wait_for_function("() => window.app.project.name === 'Mirror Show Opened'")
        _quiet(a, 2000)
        assert writes_b == [], writes_b
        # the source's map changed on A: the copy follows, written by A
        a.evaluate(PATTERN_JS, [ids['Screen1'], 'br-v'])
        srv = _settled(e2e_server, lambda p: next(l for l in p['layers'] if l['id'] == ids['Screen2'])
                       .get('flowPattern') == 'br-v')
        s1 = next(l for l in srv['layers'] if l['id'] == ids['Screen1'])
        s2 = next(l for l in srv['layers'] if l['id'] == ids['Screen2'])
        assert _mirror_settings(s2) == _mirror_settings(s1)
        # a screen added, then taken back
        a.evaluate("() => window.app.addLayer()")
        _settled(e2e_server, lambda p: len(p['layers']) == 4)
        _quiet(a)
        a.evaluate("() => window.app.undo()")
        _settled(e2e_server, lambda p: len(p['layers']) == 3)
        _quiet(a)
        b.wait_for_function("() => window.app.project.layers.length === 3")
        _quiet(b)
        assert writes_b == [], writes_b
        # A's history: its own steps, never another page's
        acts = _actions(a)
        assert FOREIGN not in acts, acts
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()


def test_a_page_joining_a_show_with_a_mirror_writes_nothing(e2e_server, pw_browser):
    """Page B opens while the show already holds a mirror whose stored
    map is behind its source's (the source changed by a script, which no
    page copied): B shows the copy as it should be and sends no write, so
    page A, already on the show, hears of no change."""
    ids = _seed(e2e_server)
    ctx_a, ctx_b = _context(pw_browser), _context(pw_browser)
    try:
        a, pa = _open(ctx_a, e2e_server)
        _make_mirror(a, ids, e2e_server)
        _call(e2e_server, 'PUT', f"/api/layer/{ids['Screen1']}", {'flowPattern': 'bl-h'})
        _quiet(a)
        before = _server(e2e_server)
        acts = _actions(a)
        writes_b = _record_writes(ctx_b)
        b, pb = _open(ctx_b, e2e_server)
        # B on Screen1 and on the copy: selecting screens is no change
        b.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))",
                   ids['Screen2'])
        b.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))",
                   ids['Screen1'])
        _quiet(b, 2000)
        assert writes_b == [], writes_b
        assert _actions(a) == acts
        after = _server(e2e_server)
        assert after['layers'] == before['layers']
        # B shows the copy's map: its source's
        flows = b.evaluate("(ids) => ids.map(id => window.app.project.layers.find(l => l.id === id).flowPattern)",
                           [ids['Screen1'], ids['Screen2']])
        assert flows == ['bl-h', 'bl-h'], flows
        # A changes the source: A writes the copy, B, following, nothing
        a.evaluate(PATTERN_JS, [ids['Screen1'], 'tr-h'])
        _settled(e2e_server, lambda p: next(l for l in p['layers'] if l['id'] == ids['Screen2'])
                 .get('flowPattern') == 'tr-h')
        _quiet(b)
        assert writes_b == [], writes_b
        assert FOREIGN not in _actions(a), _actions(a)
        assert pa == [] and pb == [], pa + pb
    finally:
        ctx_a.close()
        ctx_b.close()
