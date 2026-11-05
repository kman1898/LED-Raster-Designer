"""A reload keeps the place; a launch still starts over (1.6.0).

The report (1.6.0-beta.5, Safari): reloading the page with a show open
brought up the start page over it, and the app came back on Pixel Map
though the person had been on Power. The client log read page_load,
load_project (the show, 7 screens), start_page_open (launch) at every
reload, on the same server.

Owner, 2026-11-04: a reload brings back just the tab the person was on;
selection, canvas, zoom and pan start fresh as before. A reload does not
show the start page unless the start page was on screen (no choice made
yet) when the page went; then it comes back. A launch still always shows
the start page and starts on the default tab.

The launcher opens a new browser tab per launch, so the place is kept in
sessionStorage (one per tab, kept by a reload) and only a load the browser
calls a reload, on the server that wrote it, reads it back
(app-start-page.js resumeOrLaunch).

Only the host dialogs a page could open here are routed (save-file,
open-file, select-directory), each answered as unavailable.

Run locally (each session takes its own free port):
    python -m pytest tests/test_reload_keeps_place.py -v --browser chromium
"""

import json
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
START_PAGE = QUIET + "window.__lrdStartPage = true;"
BOTH = START_PAGE + "window.__lrdStartupPicker = true;"
# The client log, as sendClientLog beacons it, kept on the page.
CLIENT_LOG = (
    "window.__clog = [];"
    "(function () { const send = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);"
    " navigator.sendBeacon = (u, b) => { try { b.text().then(t => { const j = JSON.parse(t);"
    " window.__clog.push({ action: j.action, details: j.details }); }); } catch (e) {}"
    " return send ? send(u, b) : true; }; })();"
)
UNAVAILABLE = json.dumps({'ok': False, 'cancelled': False, 'unavailable': True})


def _post(url, path, body=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = b'' if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url + path, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=10) as reply:
        assert reply.status == 200
        return json.loads(reply.read().decode('utf-8'))


def _new_pristine_project(url):
    """What a launch finds: the server's fresh project (New)."""
    _post(url, '/api/project/new')


def _seed_show(url):
    """A show already open on the server, as in the report."""
    _new_pristine_project(url)
    _post(url, '/api/layer/add', {'name': 'Upstage', 'columns': 4, 'rows': 2,
                                  'cabinet_width': 128, 'cabinet_height': 128,
                                  'offset_x': 1200, 'offset_y': 0})
    _post(url, '/api/project', {'name': 'Reload Show'})


def _route_dialogs(page):
    for name in ('save-file', 'open-file', 'select-directory'):
        page.route(f'**/api/native-dialog/{name}', lambda route: route.fulfill(
            status=200, content_type='application/json', body=UNAVAILABLE))


def _new_context(pw_browser, init):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(CLIENT_LOG + init)
    return context


def _open_tab(context, url):
    """A launch: a new browser tab on the app."""
    pg = context.new_page()
    problems = []
    pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))
    pg.on('console', lambda m: problems.append('console: ' + m.text)
          if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
    pg.on('response', lambda r: problems.append(f'{r.status} {r.url}')
          if '/api/' in r.url and r.status >= 400 and '/api/native-dialog/' not in r.url
          and '/api/panel-catalog/refresh' not in r.url else None)
    _route_dialogs(pg)
    pg.goto(url, wait_until='domcontentloaded')
    _loaded(pg)
    return pg, problems


def _loaded(pg):
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)


def _reload(pg):
    pg.reload(wait_until='domcontentloaded')
    _loaded(pg)


def _start_up(pg):
    return pg.evaluate("() => { const m = document.getElementById('start-page-modal');"
                       " return !!m && m.style.display === 'block'; }")


def _wait_start(pg, timeout=10000):
    pg.wait_for_function("() => { const m = document.getElementById('start-page-modal');"
                         " return !!m && m.style.display === 'block'; }", timeout=timeout)


def _wait_picker(pg, timeout=10000):
    pg.wait_for_function("() => document.getElementById('preset-picker-modal').style.display === 'block'"
                         " && window.app._pickerMode === 'startup'", timeout=timeout)


def _picker_up(pg):
    return pg.evaluate("() => document.getElementById('preset-picker-modal').style.display === 'block'")


def _tab(pg):
    return pg.evaluate("() => { const t = document.querySelector('#view-tabs .view-tab.active[data-mode]');"
                       " return t ? t.dataset.mode : null; }")


def _wait_tab(pg, mode, timeout=10000):
    pg.wait_for_function("(m) => { const t = document.querySelector('#view-tabs .view-tab.active[data-mode]');"
                         " return !!t && t.dataset.mode === m && window.canvasRenderer.viewMode === m; }",
                         arg=mode, timeout=timeout)


def _click_tab(pg, mode):
    pg.locator(f'#view-tabs .view-tab[data-mode="{mode}"]').click()
    _wait_tab(pg, mode)


def _settle(pg):
    """Longer than a launch takes to put its start page up (two quiet
    300 ms looks), so a page that did not come has had its chance."""
    pg.wait_for_timeout(2500)


def _close_start_page(pg):
    pg.locator('#start-page-close').click()
    pg.wait_for_function("() => document.getElementById('start-page-modal').style.display !== 'block'",
                         timeout=5000)


def _logged(pg, action):
    return pg.evaluate("(a) => (window.__clog || []).filter(e => e.action === a).map(e => e.details)", action)


# ── (a) a reload on a show ────────────────────────────────────────────────

def test_a_reload_on_a_show_comes_back_on_its_tab_with_no_start_page(e2e_server, pw_browser):
    _seed_show(e2e_server)
    context = _new_context(pw_browser, START_PAGE)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _wait_start(pg)
        _close_start_page(pg)
        _click_tab(pg, 'power')
        _reload(pg)
        _wait_tab(pg, 'power')
        _settle(pg)
        assert not _start_up(pg)
        assert _tab(pg) == 'power'
        assert pg.evaluate("() => window.app.project.name") == 'Reload Show'
        assert pg.evaluate("() => getComputedStyle(document.querySelector("
                           "'.tab-panel[data-tab=\"power\"]')).display") != 'none'
        assert _logged(pg, 'start_page_open') == []
        # again from another tab: it follows the last one
        _click_tab(pg, 'show-look')
        _reload(pg)
        _wait_tab(pg, 'show-look')
        _settle(pg)
        assert not _start_up(pg)
        resumed = _logged(pg, 'reload_resume')
        assert resumed and resumed[-1]['tab'] == 'show-look' and resumed[-1]['pending'] is None, resumed
        assert problems == [], problems
    finally:
        context.close()


# ── (b) the start page up as the page goes ────────────────────────────────

def test_the_start_page_up_at_a_reload_comes_back_and_once_closed_stays_closed(e2e_server, pw_browser):
    _seed_show(e2e_server)
    context = _new_context(pw_browser, START_PAGE)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _wait_start(pg)
        _reload(pg)
        _wait_start(pg)
        assert _tab(pg) == 'pixel-map'
        resumed = _logged(pg, 'reload_resume')
        assert resumed and resumed[-1]['pending'] == 'launch', resumed
        # (c, over a show) X, then a reload: no start page
        _close_start_page(pg)
        _reload(pg)
        _settle(pg)
        assert not _start_up(pg)
        assert pg.evaluate("() => [window.app.project.name, window.app.project.layers.length]") == ['Reload Show', 2]
        assert problems == [], problems
    finally:
        context.close()


def test_the_picker_its_new_opened_up_at_a_reload_brings_the_start_page_back(e2e_server, pw_browser):
    _new_pristine_project(e2e_server)
    context = _new_context(pw_browser, BOTH)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _wait_start(pg)
        pg.locator('#start-page-new').click()
        _wait_picker(pg)
        _reload(pg)
        _wait_start(pg)
        assert not _picker_up(pg)
        assert pg.evaluate("() => window.app._startupTargetId === window.app.project.layers[0].id")
        assert problems == [], problems
    finally:
        context.close()


def test_file_new_s_picker_up_at_a_reload_comes_back_as_the_picker(e2e_server, pw_browser):
    _new_pristine_project(e2e_server)
    context = _new_context(pw_browser, BOTH)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _wait_start(pg)
        _close_start_page(pg)
        pg.locator('#menu-bar .menu-item[data-menu="file"]').click()
        pg.wait_for_timeout(150)
        pg.locator('#menu-file .menu-option[data-action="new"]').click()
        _wait_picker(pg)
        assert pg.evaluate("() => window.app._pickerFromStartPage") is False
        _reload(pg)
        _wait_picker(pg)
        _settle(pg)
        assert not _start_up(pg)
        assert _picker_up(pg)
        assert problems == [], problems
    finally:
        context.close()


def test_a_start_page_still_waiting_behind_a_dialog_comes_after_a_reload(e2e_server, pw_browser):
    """The launch's start page waits for the guide, What's New or another
    dialog. Reloaded before it showed, no choice was made: it comes."""
    blocker = ("document.addEventListener('DOMContentLoaded', () => {"
               " let first = false; try { first = !sessionStorage.getItem('__blocked');"
               " sessionStorage.setItem('__blocked', '1'); } catch (e) {}"
               " if (!first) return;"
               " const m = document.createElement('div'); m.id = 'test-blocker'; m.className = 'modal';"
               " m.style.display = 'block'; document.body.appendChild(m); });")
    _seed_show(e2e_server)
    context = _new_context(pw_browser, START_PAGE + blocker)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _settle(pg)
        assert not _start_up(pg)
        assert pg.evaluate("() => window.app._launchChoicePending()") == 'launch'
        _reload(pg)
        _wait_start(pg)
        assert problems == [], problems
    finally:
        context.close()


# ── (c) the emptied launch project ────────────────────────────────────────

def test_a_reload_over_the_project_the_x_emptied_keeps_it_empty(e2e_server, pw_browser):
    """X on the launch's start page leaves an empty project. The server
    puts a startup screen back on every page load; the reload takes it
    out again and shows no start page."""
    _new_pristine_project(e2e_server)
    context = _new_context(pw_browser, START_PAGE)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _wait_start(pg)
        _close_start_page(pg)
        pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
        for _ in range(2):
            _reload(pg)
            pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
            _settle(pg)
            assert not _start_up(pg)
            assert pg.evaluate("() => window.app.project.layers.length") == 0
            srv = pg.evaluate("async () => (await fetch('/api/project')).json()")
            assert srv['layers'] == [] and srv['is_pristine'] is True, srv['layers']
        assert problems == [], problems
    finally:
        context.close()


# The socket's layer_updated events held until the page's project is empty,
# then handed over: the echo of the boot's own PUT of the startup screen
# lands after the DELETE that took it out. The server holds socket sends
# while the socket upgrades from polling, which brings an echo that late
# (CI, 2026-11-04). One the page never empties for goes after 3 s, so a
# page that kept its screen fails on the count.
# A screen's PUT waits for the socket: one sent before it connected has
# no echo at all (a busy machine, 2026-11-04).
LATE_ECHO = (
    "window.__lateEchoes = 0;"
    "(function () { const send = window.fetch;"
    " window.fetch = function (u, o) {"
    " if (!(o && o.method === 'PUT' && String(u).indexOf('/api/layer/') >= 0)) return send.apply(this, arguments);"
    " return new Promise(r => { const t = setInterval(() => { const s = window.app && window.app.socket;"
    " if (s && s.connected) { clearInterval(t); r(); } }, 10); }).then(() => send.call(window, u, o)); }; })();"
    "(function () { let real; Object.defineProperty(window, 'io', { configurable: true,"
    " get() { return real; },"
    " set(v) { real = function () { const s = v.apply(this, arguments); const on = s.on.bind(s);"
    " s.on = (ev, fn) => on(ev, ev !== 'layer_updated' ? fn : (...a) => {"
    " const held = Date.now(); const t = setInterval(() => { const app = window.app;"
    " const empty = !!(app && app.project && Array.isArray(app.project.layers) && !app.project.layers.length);"
    " if (!empty && Date.now() - held < 3000) return;"
    " clearInterval(t); fn(...a); window.__lateEchoes += 1; }, 10); });"
    " return s; }; Object.assign(real, v); } }); })();"
)


def test_a_late_echo_of_the_startup_screen_never_brings_it_back(e2e_server, pw_browser):
    """The boot's PUT of the startup screen is echoed on the socket. Landing
    after the reload took that screen out, the echo put it back on the page
    (the server had none): one screen where the X left none, and the next
    reload kept it."""
    _new_pristine_project(e2e_server)
    context = _new_context(pw_browser, START_PAGE + LATE_ECHO)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _wait_start(pg)
        _close_start_page(pg)
        # The launch's X takes the same screen out under the same echo.
        pg.wait_for_function("() => window.__lateEchoes >= 1", timeout=10000)
        assert pg.evaluate("() => window.app.project.layers.length") == 0
        for _ in range(2):
            _reload(pg)
            pg.wait_for_function("() => window.__lateEchoes >= 1", timeout=10000)
            assert pg.evaluate("() => window.app.project.layers.length") == 0
            assert not _start_up(pg)
            srv = pg.evaluate("async () => (await fetch('/api/project')).json()")
            assert srv['layers'] == [] and srv['is_pristine'] is True, srv['layers']
        assert problems == [], problems
    finally:
        context.close()


# ── (d) a launch is a new browser tab ─────────────────────────────────────

def test_a_new_tab_is_a_launch_and_never_takes_another_tab_s_place(e2e_server, pw_browser):
    _seed_show(e2e_server)
    context = _new_context(pw_browser, START_PAGE)
    try:
        first, problems = _open_tab(context, e2e_server)
        _wait_start(first)
        _close_start_page(first)
        _click_tab(first, 'power')
        # A launch on the same browser: the start page, on the default tab.
        second, problems2 = _open_tab(context, e2e_server)
        _wait_start(second)
        assert _tab(second) == 'pixel-map'
        assert _logged(second, 'reload_resume') == []
        # The first tab's reload is still its own.
        _reload(first)
        _wait_tab(first, 'power')
        _settle(first)
        assert not _start_up(first)
        # The address opened again in the same tab is not a reload either.
        first.goto(e2e_server, wait_until='domcontentloaded')
        _loaded(first)
        _wait_start(first)
        assert _tab(first) == 'pixel-map'
        assert problems == [] and problems2 == [], problems + problems2
    finally:
        context.close()


# ── what a reload does not trust ──────────────────────────────────────────

def test_with_no_session_storage_a_reload_is_a_launch(e2e_server, pw_browser):
    no_storage = ("Object.defineProperty(window, 'sessionStorage', { configurable: true,"
                  " get() { throw new DOMException('blocked', 'SecurityError'); } });")
    _seed_show(e2e_server)
    context = _new_context(pw_browser, START_PAGE + no_storage)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _wait_start(pg)
        _close_start_page(pg)
        _click_tab(pg, 'power')
        _reload(pg)
        _wait_start(pg)
        assert _tab(pg) == 'pixel-map'
        assert problems == [], problems
    finally:
        context.close()


def test_a_tab_reloaded_on_another_server_is_a_launch(e2e_server, pw_browser):
    """The app quit and started again: the old tab's record names the old
    server, so its reload is a launch."""
    _seed_show(e2e_server)
    context = _new_context(pw_browser, START_PAGE)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _wait_start(pg)
        _close_start_page(pg)
        _click_tab(pg, 'power')
        pg.evaluate("() => { window.app._serverSessionId = 'a-server-gone-since'; }")
        _reload(pg)
        _wait_start(pg)
        assert _tab(pg) == 'pixel-map'
        assert problems == [], problems
    finally:
        context.close()


def test_a_tab_the_page_no_longer_shows_falls_back_to_the_default(e2e_server, pw_browser):
    hide_power_after_reload = (
        "document.addEventListener('DOMContentLoaded', () => {"
        " let n = 0; try { n = Number(sessionStorage.getItem('__loads') || 0) + 1;"
        " sessionStorage.setItem('__loads', String(n)); } catch (e) {}"
        " if (n < 2) return;"
        " const t = document.querySelector('#view-tabs .view-tab[data-mode=\"power\"]');"
        " if (t) t.style.display = 'none'; });")
    _seed_show(e2e_server)
    context = _new_context(pw_browser, START_PAGE + hide_power_after_reload)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _wait_start(pg)
        _close_start_page(pg)
        _click_tab(pg, 'power')
        _reload(pg)
        _settle(pg)
        assert _tab(pg) == 'pixel-map'
        assert not _start_up(pg)
        resumed = _logged(pg, 'reload_resume')
        assert resumed and resumed[-1]['tab'] == 'power' and resumed[-1]['tabRestored'] is False, resumed
        assert problems == [], problems
    finally:
        context.close()


def test_an_automated_browser_still_never_sees_the_start_page(e2e_server, pw_browser):
    _seed_show(e2e_server)
    context = _new_context(pw_browser, QUIET)
    try:
        pg, problems = _open_tab(context, e2e_server)
        _settle(pg)
        assert not _start_up(pg)
        _click_tab(pg, 'data-flow')
        _reload(pg)
        _wait_tab(pg, 'data-flow')
        _settle(pg)
        assert not _start_up(pg)
        assert problems == [], problems
    finally:
        context.close()
