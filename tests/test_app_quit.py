"""Quitting the app stops it, and an open page knows (owner, 2026-11-10).

"when the app is closed the web interface is still usable. it doesnt die.
that is not proper functionality". Two things were wrong:

* On macOS, the app menu's Quit and Cmd+Q reached the launcher window's
  closing handler, which treats every close as the red X: it hid the window
  and cancelled the quit, so the server went on serving every page.
* A page whose server had gone said "Disconnected" in its status bar and
  nothing else: every menu, key and edit still worked on its own copy, and
  when the app came back the page carried on with that stale copy.

Now every Quit (the launcher window's, the tray / menu-bar icon's, the
macOS app menu's and Cmd+Q, File > Quit on the host, an update's Install
and restart) ends the process, and an open page dims with "LED Raster
Designer isn't running. Start it to keep working.", takes no input, and
reloads by itself onto the server's show once the app runs again.

The browser tests here run the app's server as a process of its own on a
free port, so it can really be stopped (killed, as os._exit ends it) and
started again on the same address. File > Quit's tests use the shared
e2e server with the launcher's quit replaced by a fake.

Run locally:
    python -m pytest tests/test_app_quit.py -v --browser chromium
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import types
import urllib.request

import pytest

import updater
import routes_project

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

launcher_window = pytest.importorskip('launcher_window')

GONE_TEXT = "LED Raster Designer isn't running. Start it to keep working."
LOST_TEXT = 'Your last changes may not have been saved.'
QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"


# ── The launcher: every Quit ends the process ────────────────────────────

class _FakeWindow:
    def __init__(self):
        self.calls = []

    def destroy(self):
        self.calls.append('destroy')

    def show(self):
        self.calls.append('show')

    def hide(self):
        self.calls.append('hide')

    def evaluate_js(self, script):
        self.calls.append(('js', script))


class _FakeIcon:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


@pytest.fixture
def launcher(monkeypatch):
    """A LauncherAPI with a fake window and tray icon. os._exit records
    instead of ending the test run; the server's socket is a fake that
    records what the pages are told."""
    exits, emitted, logged = [], [], []
    monkeypatch.setattr(launcher_window.os, '_exit', lambda code: exits.append(code))
    monkeypatch.setattr(launcher_window.time, 'sleep', lambda s: None)
    monkeypatch.setattr(launcher_window, '_launcher_log',
                        lambda action, details, source='launcher': logged.append(action))
    sio = types.SimpleNamespace(emit=lambda event, data=None: emitted.append(event))
    monkeypatch.setattr(launcher_window, '_socketio', sio)
    monkeypatch.setattr(launcher_window, '_show_has_unsaved_changes', lambda: False)
    api = launcher_window.LauncherAPI({'port': 8050})
    api._window = _FakeWindow()
    api._tray_icon = _FakeIcon()
    return types.SimpleNamespace(api=api, exits=exits, emitted=emitted, logged=logged)


def test_quit_tells_the_pages_takes_the_icon_and_window_away_and_ends_the_process(launcher):
    launcher.api.quit()
    assert launcher.emitted == ['app_quitting']
    assert launcher.api._tray_icon.stopped is True
    assert launcher.api._window.calls == ['destroy']
    # The server is a thread of this process: ending it ends the server.
    assert launcher.exits == [0]


def test_a_quit_with_nothing_unsaved_quits_at_once_from_every_menu(launcher):
    for source in ('tray', 'menubar', 'app_menu', 'window'):
        launcher.exits.clear()
        assert launcher.api.request_quit(source) is None
        assert launcher.exits == [0], source


def test_a_quit_with_unsaved_changes_asks_in_the_launcher_first(launcher, monkeypatch):
    monkeypatch.setattr(launcher_window, '_show_has_unsaved_changes', lambda: True)
    started = []
    real_thread = threading.Thread

    def thread(*a, **k):
        t = real_thread(*a, **k)
        started.append(t)
        return t
    monkeypatch.setattr(launcher_window.threading, 'Thread', thread)
    assert launcher.api.request_quit('tray') == {'ask': True}
    for t in started:
        t.join(5)
    assert launcher.exits == []
    calls = launcher.api._window.calls
    assert 'show' in calls
    assert ('js', 'window.showQuitAsk && window.showQuitAsk()') in calls
    # "Quit anyway" in the window is quit(): now it goes.
    launcher.api.quit()
    assert launcher.exits == [0]


def test_the_window_s_own_quit_shows_the_question_itself(launcher, monkeypatch):
    monkeypatch.setattr(launcher_window, '_show_has_unsaved_changes', lambda: True)
    assert launcher.api.request_quit('window') == {'ask': True}
    assert launcher.exits == []
    assert not any(isinstance(c, tuple) for c in launcher.api._window.calls)


def test_with_no_launcher_window_windows_asks_in_a_message_box(launcher, monkeypatch):
    monkeypatch.setattr(launcher_window, '_show_has_unsaved_changes', lambda: True)
    monkeypatch.setattr(launcher_window.sys, 'platform', 'win32')
    launcher.api.mark_window_unavailable()
    monkeypatch.setattr(launcher_window, '_windows_quit_anyway', lambda: False)
    assert launcher.api.request_quit('tray') == {'ask': True}
    assert launcher.exits == []
    monkeypatch.setattr(launcher_window, '_windows_quit_anyway', lambda: True)
    launcher.api.request_quit('tray')
    assert launcher.exits == [0]


def test_the_tray_icon_s_quit_is_the_launcher_s_quit(monkeypatch):
    """Windows: the tray menu's Quit goes through request_quit, so it asks
    about unsaved changes and then ends the process."""
    items = {}

    class MenuItem:
        def __init__(self, text, action, default=False):
            items[text] = action

    class Menu:
        SEPARATOR = object()

        def __init__(self, *entries):
            self.entries = entries

    class Icon:
        def __init__(self, **kw):
            self.kw = kw

        def run_detached(self):
            pass

    monkeypatch.setitem(sys.modules, 'pystray', types.SimpleNamespace(Icon=Icon, Menu=Menu, MenuItem=MenuItem))
    monkeypatch.setitem(sys.modules, 'launcher_pc', types.SimpleNamespace(create_tray_icon_image=lambda: None))
    asked = []
    api = types.SimpleNamespace(show=lambda: None, open_browser=lambda: None,
                                request_quit=lambda source='launcher': asked.append(source))
    launcher_window._start_tray_windows(api)
    items['Quit LED Raster Designer'](None, None)
    assert asked == ['tray']


def applicationShouldTerminate_(handler):
    """Named as pywebview's macOS app delegate method is: the app menu's
    Quit, Cmd+Q and a logout call the closing handler from inside it."""
    return handler()


def windowShouldClose_(handler):
    """Named as pywebview's window delegate method is: the red X."""
    return handler()


def test_cmd_q_quits_and_the_red_x_only_hides(monkeypatch):
    calls = []
    done = threading.Event()

    def request_quit(source='launcher'):
        calls.append(('quit', source))
        done.set()
    api = types.SimpleNamespace(hide=lambda: calls.append('hide'), request_quit=request_quit)
    on_closing = launcher_window._on_closing_for(api)
    # the red X: hidden, the server keeps serving the other devices
    assert windowShouldClose_(on_closing) is False
    assert calls == ['hide']
    calls.clear()
    # Cmd+Q / the app menu's Quit: the app quits (asking first if unsaved)
    assert applicationShouldTerminate_(on_closing) is False
    assert done.wait(5)
    assert calls == [('quit', 'app_menu')]


def test_quit_now_is_the_launcher_s_quit_and_always_exits(monkeypatch):
    exits, quits = [], []
    monkeypatch.setattr(launcher_window.os, '_exit', lambda code: exits.append(code))
    monkeypatch.setattr(launcher_window, '_LAUNCHER_API', types.SimpleNamespace(quit=lambda: quits.append(1)))
    launcher_window.quit_now()
    assert quits == [1] and exits == [0]
    # before the window is up there is no API yet: the process still ends
    monkeypatch.setattr(launcher_window, '_LAUNCHER_API', None)
    launcher_window.quit_now()
    assert exits == [0, 0]


def test_the_launcher_hands_its_quit_to_the_server_before_it_serves(monkeypatch):
    """main() sets the quit handler before the server thread starts, so a
    page that loads before the window is up can quit (and is offered it)."""
    order = []
    monkeypatch.setattr(launcher_window, '_install_crash_logger', lambda: None)
    monkeypatch.setattr(launcher_window, '_clear_mark_of_the_web', lambda: None)
    monkeypatch.setattr(launcher_window, '_setup_launcher_debug_log', lambda: None)
    monkeypatch.setattr(launcher_window, '_log_startup_environment', lambda: None)
    monkeypatch.setattr(launcher_window, 'load_settings', lambda: {'port': 8050})
    monkeypatch.setattr(launcher_window.time, 'sleep', lambda s: None)
    monkeypatch.setattr(launcher_window, 'run_window', lambda settings: order.append('window'))
    monkeypatch.setattr(launcher_window, 'start_flask_server', lambda settings: order.append('server'))
    monkeypatch.setattr(updater, 'set_quit_handler', lambda fn: order.append(('handler', fn)))
    monkeypatch.setattr(updater, 'open_browser_on_launch', lambda settings: False)
    monkeypatch.delenv('LRD_NO_WINDOW', raising=False)
    monkeypatch.delenv('LRD_SELFTEST', raising=False)

    class _Thread:
        def __init__(self, target, args=(), daemon=None, **kw):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(launcher_window.threading, 'Thread', _Thread)
    launcher_window.main()
    assert order == [('handler', launcher_window.quit_now), 'server', 'window']


# ── The route behind File > Quit ──────────────────────────────────────────

@pytest.fixture
def quit_calls(monkeypatch):
    """A launcher to quit, faked: the route schedules the quit and nothing
    ends the test run."""
    calls = []
    monkeypatch.setattr(updater, '_quit_handler', lambda: calls.append('handler'))
    monkeypatch.setattr(updater, '_schedule_quit', lambda delay=1.0: calls.append(('scheduled', delay)))
    routes_project.set_project_unsaved(False)
    yield calls
    routes_project.set_project_unsaved(False)


REMOTE = {'REMOTE_ADDR': '10.200.1.77'}


def test_a_tablet_cannot_quit_the_app(client, quit_calls):
    res = client.post('/api/app/quit', json={'discard': True}, environ_base=REMOTE)
    assert res.status_code == 403
    assert res.get_json()['error'] == 'Only the computer running the app can quit it.'
    assert quit_calls == []


def test_the_host_quits_through_the_launcher_s_quit(client, quit_calls):
    res = client.post('/api/app/quit', json={})
    assert res.status_code == 200 and res.get_json() == {'ok': True}
    assert quit_calls == [('scheduled', 1.0)]


def test_unsaved_changes_refuse_the_quit_until_the_page_has_asked(client, quit_calls):
    routes_project.set_project_unsaved(True)
    res = client.post('/api/app/quit', json={})
    assert res.status_code == 409 and res.get_json()['unsaved'] is True
    assert quit_calls == []
    res = client.post('/api/app/quit', json={'discard': True})
    assert res.status_code == 200
    assert quit_calls == [('scheduled', 1.0)]


def test_with_no_launcher_the_route_says_so_and_stops_nothing(client, monkeypatch):
    scheduled = []
    monkeypatch.setattr(updater, '_quit_handler', None)
    monkeypatch.setattr(updater, '_schedule_quit', lambda delay=1.0: scheduled.append(delay))
    res = client.post('/api/app/quit', json={'discard': True})
    assert res.status_code == 409
    body = res.get_json()
    assert body['available'] is False and "can't be quit from here" in body['error']
    assert scheduled == []


def test_the_route_runs_the_launcher_s_own_quit(client, monkeypatch):
    """The whole chain with fakes at its ends: route, updater, quit_now,
    the launcher API's quit."""
    exits, quits = [], []
    monkeypatch.setattr(updater, '_quit_handler', launcher_window.quit_now)
    monkeypatch.setattr(updater, '_schedule_quit', lambda delay=1.0: updater._quit_app())
    monkeypatch.setattr(updater.os, '_exit', lambda code: exits.append(('updater', code)))
    monkeypatch.setattr(launcher_window.os, '_exit', lambda code: exits.append(('launcher', code)))
    monkeypatch.setattr(launcher_window, '_LAUNCHER_API', types.SimpleNamespace(quit=lambda: quits.append(1)))
    routes_project.set_project_unsaved(False)
    assert client.post('/api/app/quit', json={}).status_code == 200
    assert quits == [1]
    assert ('launcher', 0) in exits


def _menu_html(client, environ=None):
    return client.get('/', environ_base=environ or {}).get_data(as_text=True)


def test_file_quit_is_on_the_host_s_page_only(client, quit_calls):
    html = _menu_html(client)
    assert 'id="menu-quit-app"' in html
    assert 'data-label="Quit LED Raster Designer"' in html
    # last in the File menu, with a divider above it
    file_menu = html.split('<div id="menu-file"', 1)[1].split('<div id="menu-edit"', 1)[0]
    rows = [r.strip() for r in file_menu.splitlines() if r.strip().startswith('<div class="menu-')]
    assert rows[-1].startswith('<div class="menu-option" id="menu-quit-app"')
    assert rows[-2] == '<div class="menu-divider"></div>'
    assert 'id="menu-quit-app"' not in _menu_html(client, REMOTE)


def test_file_quit_is_not_offered_with_no_launcher(client, monkeypatch):
    monkeypatch.setattr(updater, '_quit_handler', None)
    assert 'id="menu-quit-app"' not in _menu_html(client)


# ── The app's server as a process that can stop ───────────────────────────

_SERVER_CODE = r'''
import json, sys
sys.path.insert(0, {src!r})
from app import app, socketio
with app.test_client() as c:
    for name in json.loads(sys.argv[1]):
        c.post('/api/layer/add', json={{'name': name, 'columns': 2, 'rows': 2,
                                        'cabinet_width': 128, 'cabinet_height': 128}})
socketio.run(app, host='127.0.0.1', port={port}, allow_unsafe_werkzeug=True, log_output=False)
'''


def _port_free(port):
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False


class AppProcess:
    """The app's server in a process of its own, on one address for its
    whole life, so a page can see it stop and start again."""

    def __init__(self, log_dir):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(('127.0.0.1', 0))
        self.port = probe.getsockname()[1]
        probe.close()
        self.url = f'http://127.0.0.1:{self.port}'
        self.proc = None
        self.log_dir = log_dir
        self.runs = 0
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def start(self, layers=()):
        assert not _listening(self.port), f'something already listens on {self.port}'
        assert _port_free(self.port), f'port {self.port} is taken'
        self.runs += 1
        log = open(os.path.join(self.log_dir, f'server-{self.port}-{self.runs}.txt'), 'w')
        code = _SERVER_CODE.format(src=SRC, port=self.port)
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        self.proc = subprocess.Popen([sys.executable, '-c', code, json.dumps(list(layers))],
                                     cwd=SRC, stdout=log, stderr=subprocess.STDOUT, env=env)
        log.close()
        deadline = time.time() + 90
        while time.time() < deadline:
            assert self.proc.poll() is None, f'the app exited at start (log in {self.log_dir})'
            try:
                with self._opener.open(self.url + '/api/server-session', timeout=2) as r:
                    if r.status == 200:
                        return json.loads(r.read())['session_id']
            except Exception:
                time.sleep(0.1)
        raise AssertionError('the app did not come up within 90 s')

    def stop(self):
        """Ends the process the way os._exit does: no goodbye to anyone."""
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(30)
        self.proc = None

    def project(self):
        with self._opener.open(self.url + '/api/project', timeout=5) as r:
            return json.loads(r.read()), r.headers.get('X-Project-Unsaved')


@pytest.fixture
def app_process(tmp_path_factory):
    log_dir = str(tmp_path_factory.mktemp('app-quit-server'))
    proc = AppProcess(log_dir)
    yield proc
    proc.stop()


def _page(pw_browser, url, **context_kw):
    context = pw_browser.new_context(**({'viewport': {'width': 1400, 'height': 900}} | context_kw))
    context.add_init_script(QUIET + """
        window.__overlaySeen = 0;
        new MutationObserver(() => {
            if (document.getElementById('server-gone-overlay')) window.__overlaySeen += 1;
        }).observe(document.documentElement, { childList: true, subtree: true });
    """)
    page = context.new_page()
    page.goto(url, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_function("() => window.app && window.app._initialLoadComplete === true", timeout=60000)
    page.wait_for_function("() => window.app.socket && window.app.socket.connected", timeout=20000)
    return context, page


OVERLAY_UP = """() => {
    const el = document.getElementById('server-gone-overlay');
    return !!el && el.getBoundingClientRect().width > 0;
}"""


def _overlay(page):
    return page.evaluate("""() => {
        const el = document.getElementById('server-gone-overlay');
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const lost = el.querySelector('#server-gone-lost');
        return {
            text: el.querySelector('#server-gone-text').textContent,
            lost: lost && !lost.hidden ? lost.textContent : null,
            covers: r.width >= innerWidth - 1 && r.height >= innerHeight - 1,
        };
    }""")


def _names(page):
    return page.evaluate("() => (window.app.project.layers || []).map(l => l.name)")


def test_the_page_dims_and_takes_no_input_once_the_app_stops(app_process, pw_browser):
    app_process.start(['Before'])
    context, page = _page(pw_browser, app_process.url)
    # a tablet on the same show
    tablet_ctx, tablet = _page(pw_browser, app_process.url,
                               viewport={'width': 820, 'height': 1180}, has_touch=True, is_mobile=True)
    try:
        assert _names(page) == ['Before']
        stopped = time.time()
        app_process.stop()
        page.wait_for_function(OVERLAY_UP, timeout=10000)
        took = time.time() - stopped
        # quick, but past the grace a blip gets
        assert 2.5 <= took <= 7.5, took
        shown = _overlay(page)
        assert shown == {'text': GONE_TEXT, 'lost': None, 'covers': True}
        tablet.wait_for_function(OVERLAY_UP, timeout=10000)
        assert _overlay(tablet)['text'] == GONE_TEXT

        # No clicks: the File menu does not open.
        box = page.locator('#menu-bar .menu-item[data-menu="file"]').bounding_box()
        page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
        assert page.evaluate("getComputedStyle(document.getElementById('menu-file')).display") == 'none'
        # No keys: Delete does not take the selected screen; nothing is focusable.
        page.keyboard.press('Delete')
        page.keyboard.press('Control+z')
        page.keyboard.type('abc')
        assert _names(page) == ['Before']
        assert page.evaluate("document.getElementById('app').inert") is True
        # No saves queued: a write is refused before it leaves the page.
        refused = page.evaluate("""() => fetch('/api/layer/1', {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: '{}'})
            .then(() => 'sent', e => String(e.message))""")
        assert refused == 'LED Raster Designer is not running'
        assert page.evaluate("document.getElementById('status-message').textContent") == 'Not running'
    finally:
        tablet_ctx.close()
        context.close()


def test_the_page_comes_back_by_itself_on_the_server_s_show(app_process, pw_browser):
    first = app_process.start(['Before'])
    context, page = _page(pw_browser, app_process.url)
    try:
        assert page.evaluate("window.app._serverSessionId") == first
        app_process.stop()
        page.wait_for_function(OVERLAY_UP, timeout=10000)
        # An edit tried behind the overlay (the page's API, past the input
        # guard) goes nowhere: it is refused, and said.
        page.evaluate("""() => { const l = window.app.project.layers[0];
            l.name = 'Stale edit'; window.app.updateLayers([l]); }""")
        page.wait_for_function("() => !document.getElementById('server-gone-lost').hidden", timeout=5000)

        second = app_process.start(['After'])
        assert second != first
        # The page reloads by itself and joins the show the app now holds.
        deadline = time.time() + 30
        state = None
        while time.time() < deadline:
            try:
                state = page.evaluate("""() => ({
                    session: window.app && window.app._serverSessionId,
                    loaded: !!(window.app && window.app._initialLoadComplete),
                    overlay: !!document.getElementById('server-gone-overlay'),
                    names: window.app && window.app.project ? window.app.project.layers.map(l => l.name) : null })""")
                if state['loaded'] and state['session'] == second:
                    break
            except Exception:
                pass    # the page is between documents
            page.wait_for_timeout(200)
        assert state and state['session'] == second, state
        assert state['overlay'] is False
        assert state['names'] == ['After']
        page.wait_for_function("() => window.app.socket && window.app.socket.connected", timeout=10000)
        # Nothing of the old page's was written over the new run's show.
        project, unsaved = app_process.project()
        assert [l['name'] for l in project['layers']] == ['After']
        assert unsaved == '0'
        # And the page works again: the File menu opens.
        page.click('#menu-bar .menu-item[data-menu="file"]')
        assert page.evaluate("getComputedStyle(document.getElementById('menu-file')).display") == 'block'
    finally:
        context.close()


def test_a_brief_blip_shows_nothing(app_process, pw_browser):
    app_process.start(['Steady'])
    context, page = _page(pw_browser, app_process.url)
    try:
        # The connection drops and socket.io's own retry brings it back.
        page.evaluate("() => window.app.socket.io.engine.close()")
        page.wait_for_function("() => window.app.socket.connected === false", timeout=5000)
        page.wait_for_function("() => window.app.socket.connected === true", timeout=10000)
        # past the grace and the check after it
        page.wait_for_timeout(5000)
        assert page.evaluate("window.__overlaySeen") == 0
        assert page.evaluate("document.getElementById('server-gone-overlay')") is None
        assert page.evaluate("window.app.serverGone()") is False
        # and writes still go out
        assert page.evaluate("""() => fetch('/api/project/unsaved', {method: 'POST',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({unsaved: false})})
            .then(r => r.status)""") == 200
    finally:
        context.close()


def test_a_write_on_its_way_when_the_app_stops_gets_the_warning(app_process, pw_browser):
    app_process.start(['Before'])
    context, page = _page(pw_browser, app_process.url)
    try:
        app_process.stop()
        # an edit made in the moment before the page knows
        page.evaluate("""() => { const l = window.app.project.layers[0];
            l.name = 'Last edit'; window.app.updateLayers([l]); }""")
        page.wait_for_function(OVERLAY_UP, timeout=10000)
        page.wait_for_function("() => !document.getElementById('server-gone-lost').hidden", timeout=5000)
        shown = _overlay(page)
        assert shown['text'] == GONE_TEXT
        assert shown['lost'] == LOST_TEXT
    finally:
        context.close()


# ── File > Quit on the host (the shared e2e server, launcher faked) ──────

@pytest.fixture
def fake_launcher(monkeypatch):
    """The launcher's quit replaced: the route schedules a quit that
    records instead of ending the test run."""
    calls = []
    monkeypatch.setattr(updater, '_quit_handler', lambda: calls.append('handler'))
    monkeypatch.setattr(updater, '_schedule_quit', lambda delay=1.0: calls.append(('scheduled', delay)))
    routes_project.set_project_unsaved(False)
    yield calls
    routes_project.set_project_unsaved(False)


@pytest.fixture(scope="module")
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _host_page(pw_browser, url, init=''):
    context = pw_browser.new_context(viewport={'width': 1400, 'height': 900})
    context.add_init_script(QUIET + init)
    page = context.new_page()
    from conftest import open_app
    open_app(page, url)
    return context, page


def _open_file_menu(page):
    page.click('#menu-bar .menu-item[data-menu="file"]')
    page.wait_for_function("getComputedStyle(document.getElementById('menu-file')).display === 'block'")


def test_file_quit_asks_then_quits_and_the_page_dims(e2e_server, _guard, fake_launcher, pw_browser):
    context, page = _host_page(pw_browser, e2e_server)
    try:
        _open_file_menu(page)
        last = page.evaluate("""() => { const m = document.getElementById('menu-file');
            const kids = [...m.children]; const n = kids.length;
            return [kids[n - 2].className, kids[n - 1].id, kids[n - 1].textContent]; }""")
        assert last == ['menu-divider', 'menu-quit-app', 'Quit LED Raster Designer']
        page.click('#menu-quit-app')
        ask = page.wait_for_selector('#quit-app-modal', timeout=5000)
        assert ask.query_selector('.app-ask-title').text_content() == 'Quit LED Raster Designer?'
        assert ask.query_selector('.app-ask-text').text_content() == \
            'Any connected tablets and computers will disconnect.'
        # Cancel: nothing happens
        page.click('#quit-app-modal button:has-text("Cancel")')
        page.wait_for_timeout(300)
        assert fake_launcher == []
        assert page.evaluate("document.getElementById('server-gone-overlay')") is None
        # Quit: the launcher's quit is scheduled and the page dims at once
        _open_file_menu(page)
        page.click('#menu-quit-app')
        page.click('#quit-app-modal button:has-text("Quit")')
        page.wait_for_function(OVERLAY_UP, timeout=5000)
        assert fake_launcher == [('scheduled', 1.0)]
        assert _overlay(page)['text'] == GONE_TEXT
    finally:
        context.close()


def test_file_quit_with_unsaved_changes_asks_save_don_t_save_or_cancel(e2e_server, _guard, fake_launcher, pw_browser):
    context, page = _host_page(pw_browser, e2e_server, "window.__lrdAskUnsaved = true;")
    try:
        page.evaluate("() => window.app.saveState('Test edit')")
        assert page.evaluate("window.app.projectHasUnsavedChanges()") is True
        _open_file_menu(page)
        page.click('#menu-quit-app')
        ask = page.wait_for_selector('#unsaved-changes-modal', timeout=5000)
        assert 'before the app quits?' in ask.query_selector('.app-ask-text').text_content()
        assert ask.query_selector('.app-ask-detail').text_content() == \
            'Any connected tablets and computers will disconnect.'
        labels = [b.text_content() for b in ask.query_selector_all('button')]
        assert labels == ['Save', "Don't Save", 'Cancel']
        # one question only: no plain Quit? before it
        assert page.evaluate("document.getElementById('quit-app-modal')") is None
        page.click('#unsaved-changes-modal button:has-text("Cancel")')
        page.wait_for_timeout(300)
        assert fake_launcher == []
        _open_file_menu(page)
        page.click('#menu-quit-app')
        page.click("#unsaved-changes-modal button:has-text(\"Don't Save\")")
        page.wait_for_function(OVERLAY_UP, timeout=5000)
        assert fake_launcher == [('scheduled', 1.0)]
    finally:
        context.close()


def test_file_quit_is_absent_on_a_page_that_cannot_quit(e2e_server, _guard, monkeypatch, pw_browser):
    monkeypatch.setattr(updater, '_quit_handler', None)
    context, page = _host_page(pw_browser, e2e_server)
    try:
        assert page.evaluate("document.getElementById('menu-quit-app')") is None
    finally:
        context.close()
