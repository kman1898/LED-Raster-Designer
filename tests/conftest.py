"""Shared pytest fixtures for LED Raster Designer tests."""

import sys
import os
import pytest

# Add src/ to path so we can import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def pytest_addoption(parser):
    """Add --browser CLI option for Playwright browser tests."""
    parser.addoption(
        "--browser", action="store", default="chromium",
        help="Browser engine for E2E tests: chromium, firefox, or webkit"
    )

import app as app_module
from app import app, socketio, _build_initial_project


@pytest.fixture()
def client():
    """Create a Flask test client with a fresh project state."""
    app.config['TESTING'] = True

    # Reset project state before each test.
    # Must set on the module directly because some endpoints reassign
    # the global (e.g. new_project, restore_project).
    # _build_initial_project() returns a v0.8-shaped dict (canvases +
    # format_version) so tests reflect real app state.
    app_module.current_project = _build_initial_project()
    app_module.next_layer_id = 1

    with app.test_client() as client:
        yield client


@pytest.fixture()
def client_with_layer(client):
    """Create a test client with one default layer already added."""
    resp = client.post('/api/layer/add', json={
        'name': 'TestScreen',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    assert resp.status_code == 200
    return client


# ── Shared browser-test (Playwright) session fixtures ─────────────────────
# Both test_browser.py and test_browser_flows.py use these, so only ONE
# Playwright driver and ONE live server exist per session (two concurrent
# sync_playwright() instances in the same thread conflict).

@pytest.fixture(scope="session")
def browser_name(request):
    return request.config.getoption("--browser", default="chromium")


@pytest.fixture(scope="session")
def e2e_server():
    """Run the real app (SocketIO server) on a background thread."""
    import time
    import threading
    import app as app_module

    app_module.current_project = _build_initial_project()
    app_module.next_layer_id = 1
    app.config['TESTING'] = True
    with app.test_client() as c:
        c.post('/api/layer/add', json={
            'name': 'Screen1',
            'columns': 4,
            'rows': 3,
            'cabinet_width': 128,
            'cabinet_height': 128,
        })

    # Each pytest session gets a port of its OWN, so any number of sessions
    # can run side by side and nobody has to wait for anybody.
    #
    # It used to be one fixed port, 15789, and "one pytest session at a time"
    # was the rule that kept it safe. The rule did not hold, and breaking it
    # did not FAIL: the server runs on a background thread, so a second
    # session's bind error ("Address already in use") died quietly in that
    # thread, the fixture slept a second and handed out the URL anyway, and
    # the second session's browser drove the FIRST session's server - its
    # project, its preferences. Pointed at a port something else held, eight
    # tests passed against a server that was not the app at all (2026-09-12).
    # Agents built polling loops to wait each other out, and those hung.
    #
    # So: no port named, take a free one. LRD_E2E_PORT still pins one for a
    # run that needs a known address - and if that port is taken the session
    # stops at once and says so, rather than testing whatever answers there.
    # The pages follow the yielded URL; nothing else names the number.
    import socket
    import urllib.request

    def _bindable(p):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(('127.0.0.1', p))
            return True
        except OSError:
            return False
        finally:
            probe.close()

    pinned = os.environ.get('LRD_E2E_PORT')
    if pinned:
        port = int(pinned)
        if not _bindable(port):
            pytest.exit(
                f'LRD_E2E_PORT={port} is already in use - another pytest session '
                f'or app holds it. Unset LRD_E2E_PORT to take a free port, or '
                f'pick another. Refusing to run the browser suites against a '
                f'server this session did not start.', returncode=3)
    else:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()

    failures = []

    def _serve():
        try:
            socketio.run(app, host='127.0.0.1', port=port,
                         allow_unsafe_werkzeug=True, log_output=False)
        except BaseException as error:          # the bind, above all
            failures.append(error)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    # Up means OUR thread is serving: it answers, and the thread that owns
    # the port is still alive. A server someone else left on the port would
    # answer too, which is why answering alone is not enough - and why a
    # fixed sleep never was.
    url = f'http://127.0.0.1:{port}'
    # The probe goes straight to loopback: urlopen() on macOS asks the
    # system for its proxy settings first, and on a CI runner that lookup
    # can fail the wait while the server is up (macos-15 failed this wait on
    # every run from 2026-09-16). A cold runner under coverage also needs
    # more than 20 s. When it still fails, the message carries the last
    # error so the next log says why instead of only that it did.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + 90
    last_error = None
    while True:
        if failures:
            pytest.exit(f'The e2e server could not start on port {port}: '
                        f'{failures[0]!r}', returncode=3)
        try:
            with opener.open(url + '/api/project', timeout=5) as reply:
                if reply.status == 200 and thread.is_alive() and not failures:
                    break
        except Exception as error:
            last_error = error
        if time.time() > deadline:
            pytest.exit(f'The e2e server on port {port} did not come up within '
                        f'90 seconds (thread alive: {thread.is_alive()}, last '
                        f'probe error: {last_error!r}).', returncode=3)
        time.sleep(0.1)
    yield url


# ── Inter-suite isolation guards ──────────────────────────────────────────
# The e2e server is ONE in-process Flask app shared by every browser suite in
# the session, and the Flask `client` fixture rebuilds the same module-global
# project and the server's preferences. A module that mutates either - groups,
# layers, distros, per-layer fields; or a preference like the engineer's name,
# the binder's sheet size, the logo - and does not put it back poisons every
# module after it:
# test_screen_group_totals' regression guard reads the live project and trips
# on a leftover group_id, and an emptied layer list kills it outright.
#
# A module that touches shared state opts in with a module-scoped autouse
# alias (autouse guarantees the guard is set up before the module's `page`
# fixture, so its restore runs AFTER context.close() — no in-flight browser
# write outlives it):
#
#     @pytest.fixture(scope="module", autouse=True)
#     def _guard(server_project_guard):
#         """Leave the shared server project the way this module found it."""
#
# Browser modules use server_project_guard (depends on e2e_server, so the
# snapshot is taken after the server seeds Screen1). Flask-client-only
# modules use flask_project_guard, which does not force the live server up.
# Same idea as test_authority_reconciliation's _restore_server_project, and
# stronger than an in-page restore PUT (test_power_undo_coverage), which can
# run before the page's last fire-and-forget write lands.

def _snapshot_project():
    import copy
    # server_preferences is shared state too, and leaks the same way the
    # project does: test_pull_list types an engineer into the pull-sheet
    # dialog, which is stored as a PREFERENCE rather than on the project,
    # and every binder sheet after it printed that engineer's initials in
    # its revision row and his name in the overview's contents
    # (2026-09-11). Snapshotting the project alone left that behind.
    return (copy.deepcopy(app_module.current_project),
            app_module.next_layer_id,
            copy.deepcopy(getattr(app_module, 'server_preferences', None)))


def _restore_project(snapshot):
    project, next_id, prefs = snapshot
    app_module.current_project, app_module.next_layer_id = project, next_id
    # save_preferences REASSIGNS app.server_preferences rather than mutating
    # it, so putting the old dict back is what restores it.
    if prefs is not None:
        app_module.server_preferences = prefs


@pytest.fixture(autouse=True)
def _flask_tests_leave_the_project_as_found(request):
    """A test that does not drive the browser still shares the live e2e
    server's project: the Flask `client` fixture, socketio.test_client and
    direct `app_module` writes all rebind the same module globals the server
    thread reads. Such a test resets them at its start and used to leave its
    own project behind - two grouped screens, W0 and W1, landed on the next
    browser module in the worker. Alphabetical order hid it; the suite runs
    in parallel split by module since 2026-09-24, and the order within a
    worker is no longer alphabetical. So every test that does not use the
    e2e server puts the project and the preferences back the way it found
    them. Browser tests are left alone: their modules carry state from one
    test to the next on purpose and restore it with server_project_guard."""
    if 'e2e_server' in request.fixturenames:
        yield
        return
    snapshot = _snapshot_project()
    yield
    _restore_project(snapshot)


@pytest.fixture(scope="module")
def server_project_guard(e2e_server):
    """Snapshot the live server's project at module start, restore at end."""
    import time
    snapshot = _snapshot_project()
    yield
    # A page's updateLayers / undo / _persistDistros writes are fire-and-
    # forget; one can still be in the server's hands right after
    # context.close(). Let stragglers land, then overwrite them.
    time.sleep(0.5)
    _restore_project(snapshot)


# ── The socket server survives flask_socketio's test client ───────────────
# socketio.test_client(app) (test_websocket, test_pristine_flag,
# test_per_tab_properties) installs itself by REPLACING two methods on the
# one shared socket server - server._send_packet and server._send_eio_packet
# become closures that push packets into the test client's queue - and
# switches async_handlers off. Its disconnect() undoes none of that. So from
# the first socket test on, every real emit (layer_updated after a PUT,
# project_data on connect) went into a dead test client's queue and the
# browser never heard it: a module that ran after a socket module got a
# page whose live socket was silent. In alphabetical order test_distro_outputs
# came before test_pristine_flag and passed; run the two the other way round
# and its reset - which relies on the server's layer_updated echo carrying
# the breakout the server wrote - came back with none (2026-09-23). Every
# browser module sorted after test_per_tab_properties has been running with
# a dead socket in CI.
#
# This fixture puts the server back after every test, so a socket test can
# run anywhere in the order. tests/test_socket_isolation.py pins it.

_SOCKET_SERVER_PATCHED = ('_send_packet', '_send_eio_packet')


def _socket_server_state():
    server = socketio.server
    own = server.__dict__
    return {
        'patched': {k: own[k] for k in _SOCKET_SERVER_PATCHED if k in own},
        'async_handlers': server.async_handlers,
        'eio_async_handlers': server.eio.async_handlers,
    }


def restore_socket_server(state):
    """Put the shared socket server back to `state` (a _socket_server_state
    record): the test client's instance-level sender mocks come off, so the
    class's real senders show through again, and the handler mode returns."""
    server = socketio.server
    for k in _SOCKET_SERVER_PATCHED:
        if k in state['patched']:
            setattr(server, k, state['patched'][k])
        else:
            server.__dict__.pop(k, None)
    server.async_handlers = state['async_handlers']
    server.eio.async_handlers = state['eio_async_handlers']


def socket_server_is_pristine():
    """True when no test-client mock sits on the shared socket server."""
    own = socketio.server.__dict__
    return not any(k in own for k in _SOCKET_SERVER_PATCHED)


@pytest.fixture(autouse=True)
def _socket_server_survives_the_test_client():
    before = _socket_server_state()
    yield
    restore_socket_server(before)


@pytest.fixture(scope="module")
def flask_project_guard():
    """server_project_guard for modules that never open a page. Safe without
    the e2e_server dependency: if the live server already exists its seeded
    state is what gets snapshotted, and if it does not, creating it later
    re-seeds the project anyway."""
    snapshot = _snapshot_project()
    yield
    _restore_project(snapshot)


@pytest.fixture(scope="session")
def pw_browser(browser_name):
    """One Playwright driver + browser for the whole session."""
    pw_api = pytest.importorskip("playwright.sync_api",
                                 reason="playwright not installed")
    with pw_api.sync_playwright() as p:
        browser = getattr(p, browser_name).launch(headless=True)
        yield browser
        browser.close()
