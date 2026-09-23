"""flask_socketio's test client replaces the shared socket server's packet
senders with mocks and never takes them off; conftest's autouse fixture
puts the server back after every test. These pin both halves: the leak the
library has, the restore the fixture does, and - the case that bit - a
browser page whose live socket still hears the server after a socket test
ran earlier in the same session (2026-09-23)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app import app, socketio  # noqa: E402

from conftest import (  # noqa: E402
    _socket_server_state, restore_socket_server, socket_server_is_pristine,
)


@pytest.fixture(scope="module", autouse=True)
def _guard(flask_project_guard):
    """Leave the shared server project the way this module found it."""


def test_the_server_is_clean_when_a_test_starts():
    # A leak from ANY earlier test in the session lands here.
    assert socket_server_is_pristine(), sorted(
        k for k in socketio.server.__dict__ if k.startswith('_send'))


def test_the_test_client_leaks_its_mocks_and_the_restore_takes_them_off():
    app.config['TESTING'] = True
    before = _socket_server_state()
    assert socket_server_is_pristine()
    ws = socketio.test_client(app)
    ws.disconnect()
    # the library's leak, so a future flask_socketio that cleans up after
    # itself shows here as a test to retire rather than a silent no-op
    assert not socket_server_is_pristine()
    assert socketio.server.async_handlers is False
    restore_socket_server(before)
    assert socket_server_is_pristine()
    assert socketio.server.async_handlers == before['async_handlers']
    assert socketio.server.eio.async_handlers == before['eio_async_handlers']
    # the class's real senders show through again
    assert socketio.server._send_packet.__func__ is type(socketio.server)._send_packet


def test_a_socket_test_in_this_test_leaves_a_mock_for_the_fixture():
    # The fixture's teardown is what the next test relies on; this one
    # deliberately leaves the mock in place so the browser test below is
    # only green if the restore ran between them.
    app.config['TESTING'] = True
    ws = socketio.test_client(app)
    ws.disconnect()
    assert not socket_server_is_pristine()


def test_a_page_still_hears_the_server_after_an_earlier_socket_test(e2e_server, pw_browser):
    pytest.importorskip("playwright.sync_api", reason="playwright not installed")
    context = pw_browser.new_context(viewport={'width': 1200, 'height': 800})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_timeout(2000)
        connected = pg.evaluate("() => !!(window.app.socket && window.app.socket.connected)")
        assert connected, 'the page never got a socket connection'
        # a PUT from the page: the server answers on the wire AND emits
        # layer_updated to every socket; the page's listener must fire
        heard = pg.evaluate("""async () => {
            const app = window.app;
            const id = app.project.layers[0].id;
            const got = new Promise(res => {
                app.socket.once('layer_updated', l => res(l && l.id));
                setTimeout(() => res(null), 4000);
            });
            await fetch(`/api/layer/${id}?edited=1`, {
                method: 'PUT', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ name: 'Heard' })});
            return await got;
        }""")
        assert heard is not None, 'layer_updated never reached the page: the socket server is still mocked'
    finally:
        context.close()
