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

    # One fixed port so browser runs serialize on it (one pytest session at
    # a time). LRD_E2E_PORT overrides it for a session that must not share
    # the machine's default with another worktree's run - the pages follow
    # the yielded URL, nothing else names the number.
    port = int(os.environ.get('LRD_E2E_PORT') or 15789)
    thread = threading.Thread(
        target=lambda: socketio.run(app, host='127.0.0.1', port=port,
                                    allow_unsafe_werkzeug=True, log_output=False),
        daemon=True,
    )
    thread.start()
    time.sleep(1)
    yield f'http://127.0.0.1:{port}'


# ── Inter-suite isolation guards ──────────────────────────────────────────
# The e2e server is ONE in-process Flask app shared by every browser suite in
# the session, and the Flask `client` fixture rebuilds the same module-global
# project. A module that mutates the served project (groups, layers, distros,
# per-layer fields) and does not put it back poisons every module after it:
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
    return copy.deepcopy(app_module.current_project), app_module.next_layer_id


def _restore_project(snapshot):
    app_module.current_project, app_module.next_layer_id = snapshot


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
