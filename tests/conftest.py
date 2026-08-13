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

    port = 15789  # Unlikely to collide
    thread = threading.Thread(
        target=lambda: socketio.run(app, host='127.0.0.1', port=port,
                                    allow_unsafe_werkzeug=True, log_output=False),
        daemon=True,
    )
    thread.start()
    time.sleep(1)
    yield f'http://127.0.0.1:{port}'


@pytest.fixture(scope="session")
def pw_browser(browser_name):
    """One Playwright driver + browser for the whole session."""
    pw_api = pytest.importorskip("playwright.sync_api",
                                 reason="playwright not installed")
    with pw_api.sync_playwright() as p:
        browser = getattr(p, browser_name).launch(headless=True)
        yield browser
        browser.close()
