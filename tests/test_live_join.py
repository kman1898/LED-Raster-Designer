"""A launch is once per server run; every later page joins the live show.

Owner, 2026-11-09: "when using the app on my computer and then opening it
in another tab or on another machine by routing to the IP address, it
opens up the open project window, which is not correct. It should only do
that on the app originally opening. Treated like a live service once it
is already running."

The server keeps the rule (routes_project.py _claim_launch): each page
asks once at boot, the first page on the host to ask gets the start page,
a page from another machine never does, and the question stays open until
somebody answers it (the X, a pick or Cancel in the startup picker, File >
New, a show opened). The launch page's reload keeps its claim; one closed
with the start page up gives it to the next page on the host once its
socket has been gone a moment. A joining page gets no start page, no
launch picker and no first-run guide, and shows the project exactly as
the server holds it, an empty one included.

conftest starts every test as a fresh server run (new_server_run).

Run locally (each session takes its own free port):
    python -m pytest tests/test_live_join.py -v --browser chromium
"""

import json
import threading
import urllib.request

import pytest

import routes_project
from conftest import new_server_run


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
START_PAGE = QUIET + "window.__lrdStartPage = true;"
BOTH = START_PAGE + "window.__lrdStartupPicker = true;"
# A real browser: no navigator.webdriver, so the launch UI comes up as it
# does for a person.
REAL = "Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => false, configurable: true });"
FIRST_RUN_KEY = 'lrd_quickstart_first_run_done'
UNAVAILABLE = json.dumps({'ok': False, 'cancelled': True})


# ── the server's rule, through its routes ─────────────────────────────────

def _claim(c, page, prior=None, addr='127.0.0.1'):
    body = {'page': page}
    if prior is not None:
        body['prior'] = prior
    res = c.post('/api/launch/claim', json=body, environ_base={'REMOTE_ADDR': addr})
    assert res.status_code == 200, res.data
    return res.get_json()


def test_the_first_page_on_the_host_is_the_launch_and_the_next_joins(client):
    new_server_run()
    assert _claim(client, 'a') == {'startPage': True, 'why': 'first'}
    assert _claim(client, 'b') == {'startPage': False, 'why': 'joined'}
    # the launch page asking again is still the launch
    assert _claim(client, 'a')['startPage'] is True


def test_a_page_from_another_machine_never_gets_the_start_page(client):
    new_server_run()
    assert _claim(client, 'tablet', addr='10.200.1.77') == {'startPage': False, 'why': 'remote'}
    # and it did not use up the launch: the host's window still gets it
    assert _claim(client, 'host')['startPage'] is True


def test_the_launch_page_s_reload_keeps_the_claim(client):
    new_server_run()
    assert _claim(client, 'a')['startPage'] is True
    assert _claim(client, 'a2', prior=['a']) == {'startPage': True, 'why': 'reload'}
    # the old id names nobody now
    assert _claim(client, 'x', prior=['a'])['startPage'] is False
    # a reload that went before its own claim was answered names both
    assert _claim(client, 'a3', prior=['zz', 'a2'])['startPage'] is True


def test_an_answer_closes_the_question_for_every_page(client):
    new_server_run()
    assert _claim(client, 'a')['startPage'] is True
    assert client.post('/api/launch/settle', json={'why': 'test'}).get_json() == {'settled': True}
    assert _claim(client, 'a2', prior=['a']) == {'startPage': False, 'why': 'settled'}
    assert _claim(client, 'b') == {'startPage': False, 'why': 'settled'}


def test_a_launch_page_gone_without_an_answer_hands_on_over_the_startup_project(client, monkeypatch):
    new_server_run()
    assert _claim(client, 'a')['startPage'] is True
    # still within the moment a reload takes: the next page joins
    assert _claim(client, 'b')['startPage'] is False
    monkeypatch.setattr(routes_project, 'LAUNCH_GONE_SECONDS', 0.0)
    assert _claim(client, 'c') == {'startPage': True, 'why': 'took_over'}
    # a live socket keeps a launch page in place however long it stands
    routes_project.launch_socket_connected('c', 'sid-c')
    assert _claim(client, 'd') == {'startPage': False, 'why': 'joined'}
    routes_project.launch_socket_gone('sid-c')
    assert _claim(client, 'd')['startPage'] is True


def test_a_launch_page_gone_after_the_show_moved_on_closes_the_question(client, monkeypatch):
    new_server_run()
    assert _claim(client, 'a')['startPage'] is True
    client.post('/api/layer/add', json={'name': 'Worked', 'columns': 2, 'rows': 2,
                                        'cabinet_width': 128, 'cabinet_height': 128})
    monkeypatch.setattr(routes_project, 'LAUNCH_GONE_SECONDS', 0.0)
    assert _claim(client, 'b') == {'startPage': False, 'why': 'moved_on'}
    assert routes_project.launch_settled() is True


def test_pages_asking_at_the_same_moment_get_one_start_page():
    import app as app_module
    for _ in range(5):
        new_server_run()
        answers = []
        gate = threading.Barrier(12)

        def ask(n):
            with app_module.app.test_client() as c:
                gate.wait()
                answers.append(_claim(c, f'p{n}')['startPage'])

        threads = [threading.Thread(target=ask, args=(n,)) for n in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        assert len(answers) == 12
        assert answers.count(True) == 1, answers


def test_a_page_load_adds_no_startup_screen_once_the_launch_is_answered(client):
    new_server_run()
    client.post('/api/project/new')
    proj = client.get('/api/project').get_json()
    client.delete(f"/api/layer/{proj['layers'][0]['id']}?keep_pristine=1")
    assert client.get('/api/project').get_json()['layers'] == []
    # unanswered: a page load still makes the startup screen (the launch
    # page's own reload takes it out again, app-start-page resumeOrLaunch)
    client.get('/')
    assert len(client.get('/api/project').get_json()['layers']) == 1
    client.delete(f"/api/layer/{client.get('/api/project').get_json()['layers'][0]['id']}?keep_pristine=1")
    client.post('/api/launch/settle', json={'why': 'test'})
    client.get('/')
    srv = client.get('/api/project').get_json()
    assert srv['layers'] == [] and srv['is_pristine'] is True


# ── in the browser ────────────────────────────────────────────────────────

def _post(url, path, body=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = b'' if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url + path, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=10) as reply:
        assert reply.status == 200
        return json.loads(reply.read().decode('utf-8'))


def _server_project(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url + '/api/project', timeout=10) as reply:
        return json.loads(reply.read().decode('utf-8'))


def _fresh_launch(url):
    """What the app starts on: a fresh project, a fresh run."""
    _post(url, '/api/project/new')
    new_server_run()


def _context(pw_browser, init):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(init)
    for name in ('save-file', 'open-file', 'select-directory'):
        context.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json', body=UNAVAILABLE))
    return context


def _unload_race(text):
    """The browser's note that the server's last socket message crossed the
    socket's close. The app never closes its socket itself (no disconnect()
    in src/static/js), so this comes only from the page a reload is
    leaving, as a live-sync message goes out to every page."""
    return text.startswith('WebSocket connection to') and 'Data frame received after close' in text


def _watch(pg):
    problems = []
    pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))
    pg.on('console', lambda m: problems.append('console: ' + m.text)
          if m.type == 'error' and not m.text.startswith('Failed to load resource')
          and not _unload_race(m.text) else None)
    pg.on('response', lambda r: problems.append(f'{r.status} {r.url}')
          if '/api/' in r.url and r.status >= 400 and '/api/native-dialog/' not in r.url
          and '/api/panel-catalog/refresh' not in r.url else None)
    return problems


def _loaded(pg):
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)


def _open(context, url):
    pg = context.new_page()
    problems = _watch(pg)
    pg.goto(url, wait_until='domcontentloaded')
    _loaded(pg)
    return pg, problems


def _start_up(pg):
    return pg.evaluate("() => window.app.startPageOpen()")


def _wait_start(pg, timeout=10000):
    pg.wait_for_function("() => window.app.startPageOpen()", timeout=timeout)


def _picker_up(pg):
    return pg.evaluate("() => document.getElementById('preset-picker-modal').style.display === 'block'"
                       " && window.app._pickerMode === 'startup'")


def _settle(pg):
    """Longer than a launch takes to put its start page up (two quiet
    300 ms looks), so a page that did not come has had its chance."""
    pg.wait_for_timeout(2500)


def _role(pg):
    pg.wait_for_function("() => window.app._launchRole !== undefined", timeout=10000)
    return pg.evaluate("() => window.app._launchRole")


def _layers(pg):
    return pg.evaluate("() => window.app.project.layers.map(l => l.name)")


def _guide_visible(pg):
    return pg.evaluate("() => { const q = window.QuickStart; try { return !!(q && q.state().visible); }"
                       " catch (e) { return false; } }")


def test_the_first_page_gets_the_start_page_and_a_second_joins_the_live_show(e2e_server, pw_browser):
    """The second page comes while the first still stands on its start
    page: no start page, no picker, and the live project as the server
    holds it."""
    _fresh_launch(e2e_server)
    first_ctx = _context(pw_browser, BOTH)
    second_ctx = _context(pw_browser, BOTH)
    try:
        first, problems = _open(first_ctx, e2e_server)
        _wait_start(first)
        assert _role(first) == 'launch'
        second, more = _open(second_ctx, e2e_server)
        _settle(second)
        assert _role(second) == 'join'
        assert not _start_up(second) and not _picker_up(second)
        assert second.evaluate("() => window.app._launchChoicePending()") is None
        srv = _server_project(e2e_server)
        assert _layers(second) == [l['name'] for l in srv['layers']] == ['Screen1']
        # the first page's start page is untouched by the join
        assert _start_up(first)
        # and the first page's choice still works: New, a pick
        first.locator('#start-page-new').click()
        first.wait_for_function("() => document.getElementById('preset-picker-modal').style.display === 'block'")
        first.locator('#panel-catalog-list .panel-catalog-row').first.click()
        first.locator('#preset-picker-add').click()
        first.wait_for_function("() => !window.app.startPageOpen()"
                                " && document.getElementById('preset-picker-modal').style.display !== 'block'")
        # a third page after the choice: none either
        third, most = _open(second_ctx, e2e_server)
        _settle(third)
        assert not _start_up(third) and not _picker_up(third)
        assert problems == [] and more == [] and most == [], problems + more + most
    finally:
        first_ctx.close()
        second_ctx.close()


def test_another_tab_in_the_same_browser_joins(e2e_server, pw_browser):
    _fresh_launch(e2e_server)
    context = _context(pw_browser, START_PAGE)
    try:
        first, problems = _open(context, e2e_server)
        _wait_start(first)
        second, more = _open(context, e2e_server)
        _settle(second)
        assert not _start_up(second)
        assert _start_up(first)
        assert problems == [] and more == [], problems + more
    finally:
        context.close()


def test_two_pages_loading_at_once_get_one_start_page(e2e_server, pw_browser):
    for _ in range(3):
        _fresh_launch(e2e_server)
        contexts = [_context(pw_browser, START_PAGE) for _ in range(3)]
        try:
            pages = [c.new_page() for c in contexts]
            for pg in pages:
                pg.goto('about:blank')
            # every navigation started before any page has asked
            for pg in pages:
                pg.evaluate("(u) => { setTimeout(() => { location.href = u; }, 0); }", e2e_server)
            for pg in pages:
                pg.wait_for_url(e2e_server + '/', timeout=20000)
                _loaded(pg)
            for pg in pages:
                _settle(pg)
            roles = [_role(pg) for pg in pages]
            shown = [_start_up(pg) for pg in pages]
            assert roles.count('launch') == 1, roles
            assert shown == [r == 'launch' for r in roles], (roles, shown)
        finally:
            for c in contexts:
                c.close()


def test_the_launch_page_s_reload_keeps_its_start_page_and_a_joined_page_s_does_not(e2e_server, pw_browser):
    _fresh_launch(e2e_server)
    first_ctx = _context(pw_browser, START_PAGE)
    second_ctx = _context(pw_browser, START_PAGE)
    try:
        first, problems = _open(first_ctx, e2e_server)
        _wait_start(first)
        second, more = _open(second_ctx, e2e_server)
        for _ in range(2):
            first.reload(wait_until='domcontentloaded')
            _loaded(first)
            _wait_start(first)
            assert _role(first) == 'launch'
        second.reload(wait_until='domcontentloaded')
        _loaded(second)
        _settle(second)
        assert not _start_up(second)
        # the reloaded launch page still answers for the run: its X leaves
        # an empty project, and every page then has it empty
        first.locator('#start-page-close').click()
        first.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
        third, most = _open(second_ctx, e2e_server)
        _settle(third)
        assert not _start_up(third)
        assert _layers(third) == []
        assert _server_project(e2e_server)['layers'] == []
        assert problems == [] and more == [] and most == [], problems + more + most
    finally:
        first_ctx.close()
        second_ctx.close()


def test_a_reload_after_a_show_opened_shows_no_start_page(e2e_server, pw_browser):
    _fresh_launch(e2e_server)
    context = _context(pw_browser, START_PAGE)
    try:
        pg, problems = _open(context, e2e_server)
        _wait_start(pg)
        pg.evaluate("""async () => {
            const app = window.app;
            const file = JSON.parse(app.serializeProjectForFile(JSON.parse(JSON.stringify(app.project))));
            file.name = 'Opened Show';
            await app._openProjectData(file, { source: 'file' });
        }""")
        pg.wait_for_function("() => window.app.project.name === 'Opened Show' && !window.app.startPageOpen()",
                             timeout=10000)
        pg.reload(wait_until='domcontentloaded')
        _loaded(pg)
        _settle(pg)
        assert not _start_up(pg)
        assert pg.evaluate("() => window.app.project.name") == 'Opened Show'
        assert problems == [], problems
    finally:
        context.close()


def test_a_show_opened_on_a_joined_page_answers_the_launch(e2e_server, pw_browser):
    """The tablet opened the show: the launch page's reload comes back to
    the show with no start page."""
    _fresh_launch(e2e_server)
    first_ctx = _context(pw_browser, START_PAGE)
    second_ctx = _context(pw_browser, START_PAGE)
    try:
        first, problems = _open(first_ctx, e2e_server)
        _wait_start(first)
        second, more = _open(second_ctx, e2e_server)
        second.evaluate("""async () => {
            const app = window.app;
            const file = JSON.parse(app.serializeProjectForFile(JSON.parse(JSON.stringify(app.project))));
            file.name = 'Tablet Show';
            await app._openProjectData(file, { source: 'file' });
        }""")
        second.wait_for_function("() => window.app.project.name === 'Tablet Show'", timeout=10000)
        first.reload(wait_until='domcontentloaded')
        _loaded(first)
        _settle(first)
        assert not _start_up(first)
        assert first.evaluate("() => window.app.project.name") == 'Tablet Show'
        assert problems == [] and more == [], problems + more
    finally:
        first_ctx.close()
        second_ctx.close()


def test_file_new_on_a_joined_page_still_opens_the_picker(e2e_server, pw_browser):
    _fresh_launch(e2e_server)
    first_ctx = _context(pw_browser, BOTH)
    second_ctx = _context(pw_browser, BOTH)
    try:
        first, problems = _open(first_ctx, e2e_server)
        _wait_start(first)
        second, more = _open(second_ctx, e2e_server)
        _settle(second)
        assert not _start_up(second) and not _picker_up(second)
        second.locator('#menu-bar .menu-item[data-menu="file"]').click()
        second.wait_for_timeout(150)
        second.locator('#menu-file .menu-option[data-action="new"]').click()
        second.wait_for_function("() => document.getElementById('preset-picker-modal').style.display === 'block'"
                                 " && window.app._pickerMode === 'startup'", timeout=10000)
        assert not _start_up(second)
        # File > New answered the launch: the first page's reload has no
        # start page, and a new page none either
        first.reload(wait_until='domcontentloaded')
        _loaded(first)
        _settle(first)
        assert not _start_up(first)
        assert problems == [] and more == [], problems + more
    finally:
        first_ctx.close()
        second_ctx.close()


def test_file_new_on_the_launch_page_still_opens_the_picker(e2e_server, pw_browser):
    _fresh_launch(e2e_server)
    context = _context(pw_browser, BOTH)
    try:
        pg, problems = _open(context, e2e_server)
        _wait_start(pg)
        pg.locator('#start-page-close').click()
        pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
        pg.locator('#menu-bar .menu-item[data-menu="file"]').click()
        pg.wait_for_timeout(150)
        pg.locator('#menu-file .menu-option[data-action="new"]').click()
        pg.wait_for_function("() => document.getElementById('preset-picker-modal').style.display === 'block'"
                             " && window.app._pickerMode === 'startup'", timeout=10000)
        assert problems == [], problems
    finally:
        context.close()


def test_a_launch_page_closed_with_its_start_page_up_hands_it_to_the_next(e2e_server, pw_browser, monkeypatch):
    """The only page closed before anyone chose, the app's window opened
    again: the start page is still to come, for the next page on the host
    once the closed one's socket is gone."""
    monkeypatch.setattr(routes_project, 'LAUNCH_GONE_SECONDS', 0.5)
    _fresh_launch(e2e_server)
    context = _context(pw_browser, START_PAGE)
    try:
        first, problems = _open(context, e2e_server)
        _wait_start(first)
        first.close()
        page = context.new_page()
        problems2 = _watch(page)
        # the socket's goodbye and the grace both pass
        page.wait_for_timeout(1500)
        page.goto(e2e_server, wait_until='domcontentloaded')
        _loaded(page)
        _wait_start(page)
        assert _layers(page) == ['Screen1']
        assert problems == [] and problems2 == [], problems + problems2
    finally:
        context.close()


def test_no_first_run_guide_on_a_joining_page(e2e_server, pw_browser):
    """A tablet that never ran the app joins: no guide, its first run is
    left to come, and Help still offers the guide."""
    _fresh_launch(e2e_server)
    host_ctx = _context(pw_browser, REAL + QUIET)
    tablet_ctx = _context(pw_browser, REAL)
    try:
        host, problems = _open(host_ctx, e2e_server)
        _wait_start(host, 20000)
        tablet, more = _open(tablet_ctx, e2e_server)
        tablet.wait_for_function("() => window.QuickStart && !window.QuickStart.autoPending()", timeout=20000)
        tablet.wait_for_timeout(1500)
        assert not _guide_visible(tablet)
        assert not _start_up(tablet)
        assert tablet.evaluate("(k) => localStorage.getItem(k)", FIRST_RUN_KEY) == '0'
        assert tablet.locator('#menu-help .menu-option[data-action="quick-start"]').count() == 1
        assert problems == [] and more == [], problems + more
    finally:
        host_ctx.close()
        tablet_ctx.close()


def test_a_tablet_at_the_computer_s_address_joins_live(e2e_server, pw_browser, monkeypatch):
    """A page from another machine (the address check says so, as it does
    for a tablet at the computer's IP) joins with no start page, even as
    the first page of the run, and leaves the launch to the host: the
    host's own first page still gets the start page, and the tablet's
    reload still joins."""
    import routes_dialog
    _fresh_launch(e2e_server)
    tablet_ctx = _context(pw_browser, BOTH)
    host_ctx = _context(pw_browser, BOTH)
    try:
        monkeypatch.setattr(routes_dialog, '_is_same_machine', lambda addr: False)
        claims = []
        tablet = tablet_ctx.new_page()
        problems = _watch(tablet)
        tablet.on('response', lambda r: claims.append(r.json()) if r.url.endswith('/api/launch/claim') else None)
        tablet.goto(e2e_server, wait_until='domcontentloaded')
        _loaded(tablet)
        _settle(tablet)
        assert _role(tablet) == 'join'
        assert claims == [{'startPage': False, 'why': 'remote'}], claims
        assert not _start_up(tablet) and not _picker_up(tablet)
        assert _layers(tablet) == [l['name'] for l in _server_project(e2e_server)['layers']] == ['Screen1']
        tablet.reload(wait_until='domcontentloaded')
        _loaded(tablet)
        _settle(tablet)
        assert not _start_up(tablet) and not _picker_up(tablet)
        assert claims[-1] == {'startPage': False, 'why': 'remote'}, claims
        monkeypatch.undo()
        host, more = _open(host_ctx, e2e_server)
        _wait_start(host)
        assert _role(host) == 'launch'
        assert not _start_up(tablet)
        assert problems == [] and more == [], problems + more
    finally:
        tablet_ctx.close()
        host_ctx.close()


# ── a guide in one tab, the show joined in another ────────────────────────

STASH_KEY = 'lrd_tour_saved_world'


def _seed_person_s_show(url):
    """The person's own show: one wall the guide's demo does not have."""
    _post(url, '/api/project/new')
    proj = _server_project(url)
    _post(url, '/api/layer/add', {'name': 'MY WALL', 'columns': 3, 'rows': 2,
                                   'cabinet_width': 128, 'cabinet_height': 128})
    for layer in proj['layers']:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(f"{url}/api/layer/{layer['id']}", method='DELETE')
        with opener.open(req, timeout=10) as reply:
            assert reply.status == 200
    names = [l['name'] for l in _server_project(url)['layers']]
    assert names == ['MY WALL'], names


def _server_layer_names(url):
    return [l['name'] for l in _server_project(url)['layers']]


def _wait_server(url, want, timeout=20.0):
    import time
    deadline = time.time() + timeout
    names = None
    while time.time() < deadline:
        names = _server_layer_names(url)
        if want(names):
            return names
        time.sleep(0.2)
    raise AssertionError(f'the server project never got there: {names}')


def _start_guide(pg, url):
    """The guide up on its demo show, its stash written. On a slow run it
    says where it stood."""
    import time
    pg.evaluate("() => { window.QuickStart.setSpeed(4); window.QuickStart.start(); }")
    deadline = time.time() + 30
    st = None
    while time.time() < deadline:
        st = pg.evaluate("""() => { const q = window.QuickStart.state();
            return { visible: q.visible, running: q.running, index: q.index, phase: q.phase,
                     stash: !!localStorage.getItem('lrd_tour_saved_world'),
                     layers: window.app.project.layers.map(l => l.name) }; }""")
        if st['visible'] and st['stash'] and 'DEMO WALL' in st['layers']:
            break
        time.sleep(0.25)
    else:
        raise AssertionError(f'the guide did not come up: {st}')
    _wait_server(url, lambda n: 'DEMO WALL' in n and 'MY WALL' not in n)


def test_a_tab_opened_during_a_guide_leaves_the_guide_s_show_alone(e2e_server, pw_browser):
    """The guide in the first tab runs on its demo show; a second tab of
    the same browser finds the guide's stash of the person's project and
    must not put it back mid-guide. The guide's own end puts it back, and
    the second tab follows."""
    _seed_person_s_show(e2e_server)
    context = _context(pw_browser, QUIET)
    try:
        first, problems = _open(context, e2e_server)
        _start_guide(first, e2e_server)
        second, more = _open(context, e2e_server)
        _settle(second)
        second.wait_for_timeout(2000)
        assert 'DEMO WALL' in _server_layer_names(e2e_server)
        assert 'MY WALL' not in _server_layer_names(e2e_server)
        assert first.evaluate("() => window.QuickStart.state().visible")
        assert second.evaluate("(k) => !!localStorage.getItem(k)", STASH_KEY)
        assert 'DEMO WALL' in _layers(second)
        # a guide started in the second tab now would stash the demo as
        # the person's world: it says why and does not start
        second.evaluate("() => window.QuickStart.start()")
        second.wait_for_timeout(500)
        assert not second.evaluate("() => window.QuickStart.state().visible")
        assert 'DEMO WALL' in _server_layer_names(e2e_server)
        # the guide ends where it runs: the person's project comes back
        first.evaluate("() => window.QuickStart.end()")
        _wait_server(e2e_server, lambda n: n == ['MY WALL'])
        first.wait_for_function("(k) => !localStorage.getItem(k)", arg=STASH_KEY, timeout=10000)
        # the second tab never puts anything back on its own later, and
        # its reload opens on the person's project
        second.wait_for_timeout(2500)
        assert _server_layer_names(e2e_server) == ['MY WALL']
        second.reload(wait_until='domcontentloaded')
        _loaded(second)
        _settle(second)
        assert _layers(second) == ['MY WALL']
        assert _server_layer_names(e2e_server) == ['MY WALL']
        assert problems == [] and more == [], problems + more
    finally:
        context.close()


def test_a_guide_s_tab_closed_mid_guide_hands_the_project_back_through_the_other_tab(e2e_server, pw_browser):
    """The guide's tab goes before its guide ends: the tab still open puts
    the person's project back, once the closed tab has had the moment its
    own reload would take."""
    _seed_person_s_show(e2e_server)
    context = _context(pw_browser, QUIET)
    try:
        first, problems = _open(context, e2e_server)
        _start_guide(first, e2e_server)
        second, more = _open(context, e2e_server)
        _settle(second)
        assert 'DEMO WALL' in _server_layer_names(e2e_server)
        first.close()
        _wait_server(e2e_server, lambda n: n == ['MY WALL'], timeout=20.0)
        second.wait_for_function("(k) => !localStorage.getItem(k)", arg=STASH_KEY, timeout=10000)
        # the page that put it back has it
        second.wait_for_function("() => window.app.project.layers.map(l => l.name).join() === 'MY WALL'",
                                 timeout=10000)
        assert more == [], more
    finally:
        context.close()
