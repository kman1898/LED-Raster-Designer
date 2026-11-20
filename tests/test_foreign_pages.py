"""Only the app's own pages read or change the show (app.py
refuse_foreign_pages, routes_dialog page_reason).

A page on any other site, open in a browser on the computer running the app
or on the LAN, can send requests to the app, and a form or a body-less POST
goes without the browser asking first. A site whose name is pointed at the
computer after its page loaded reads every answer. So every /api/ route and
the socket's handshake ask what the browser says sent the request (Origin,
Sec-Fetch-Site, Referer) and the Host it names, and refuse anything but the
app's own pages: the designer on this computer at localhost, 127.0.0.1 or
[::1], a laptop or tablet joined over the LAN address, the IDM phone page,
the output window. The page HTML and static files stay open, so a link or
a QR code from anywhere still opens the app.
"""
import json
import socket
import threading

import pytest

import app as app_module
import routes_dialog

FOREIGN_ORIGIN = 'http://evil.example'
LAN = '192.168.1.20'   # the LAN address a laptop or phone joins on


@pytest.fixture()
def refusals(monkeypatch):
    """Every refusal line, instead of the real log file; a fresh count."""
    lines = []
    monkeypatch.setattr(routes_dialog, 'log_event',
                        lambda action, details=None, **kw: lines.append((action, details)))
    monkeypatch.setattr(routes_dialog, '_refusals', {})
    return lines


def _api_requests():
    """(method, url) for every /api/ route in the app, its arguments filled
    with a placeholder: a new route is in this list the day it is added."""
    from werkzeug.routing import IntegerConverter, FloatConverter
    out = []
    adapter = app_module.app.url_map.bind('localhost')
    for rule in app_module.app.url_map.iter_rules():
        if not rule.rule.startswith('/api/'):
            continue
        values = {}
        for name, conv in rule._converters.items():
            values[name] = 1 if isinstance(conv, (IntegerConverter, FloatConverter)) else 'x'
        for method in sorted(rule.methods - {'HEAD', 'OPTIONS'}):
            out.append((method, adapter.build(rule.endpoint, values, method=method)))
    return out


FOREIGN = [
    pytest.param({'Origin': FOREIGN_ORIGIN}, 'http://localhost', id='other-site'),
    pytest.param({'Origin': 'http://localhost:9'}, 'http://localhost', id='other-port'),
    pytest.param({'Origin': 'null'}, 'http://localhost', id='null-origin'),
    pytest.param({'Sec-Fetch-Site': 'cross-site'}, 'http://localhost', id='cross-site'),
    pytest.param({'Referer': FOREIGN_ORIGIN + '/page'}, 'http://localhost', id='referer'),
    # a site's name pointed at this computer after its page loaded
    pytest.param({'Origin': 'http://evil.example:8050'}, 'http://evil.example:8050', id='rebound-name'),
    pytest.param({}, 'http://evil.example:8050', id='rebound-name-no-origin'),
]


@pytest.mark.parametrize('headers,base', FOREIGN)
def test_every_api_route_refuses_a_page_from_another_site(client, refusals, headers, base):
    requests = _api_requests()
    assert len(requests) > 100, len(requests)
    before = json.dumps(app_module.current_project, sort_keys=True, default=str)
    let_through = []
    for method, url in requests:
        res = client.open(url, method=method, base_url=base, headers=headers,
                          data='{}', content_type='text/plain',
                          environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
        if res.status_code != 403:
            let_through.append((method, url, res.status_code))
    assert let_through == []
    # nothing reached a route
    assert json.dumps(app_module.current_project, sort_keys=True, default=str) == before
    # one line for each, but the page log's own (counted, never written)
    logged = [d for a, d in refusals if a == 'request_rejected_foreign_page']
    assert len(logged) == min(len([r for r in requests if r[1] != '/api/log']),
                              routes_dialog._REFUSAL_LINES)
    assert {d['reason'] for d in logged} <= {'host', 'origin', 'cross-site', 'referer'}


OWN_READS = ['/api/project', '/api/server-session', '/api/preferences', '/api/idm-phone/show']


@pytest.mark.parametrize('base', [
    'http://localhost:8050', 'http://127.0.0.1:8050', 'http://[::1]:8050',
    f'http://{LAN}:8050', 'https://127.0.0.1:8050',
    'http://' + socket.gethostname().lower() + ':8050',
    'http://' + socket.gethostname().lower() + '.local:8050',
    'http://' + socket.gethostname().lower() + '.lan:8050',
])
def test_the_app_s_own_pages_read_the_show_at_every_address(client, refusals, base):
    """The designer at localhost, 127.0.0.1, [::1], over HTTPS, a laptop or
    phone at the LAN address or this computer's name."""
    page = {'Referer': base + '/', 'Sec-Fetch-Site': 'same-origin'}   # a GET sends no Origin
    for url in OWN_READS:
        res = client.get(url, base_url=base, headers=page)
        assert res.status_code == 200, (url, res.status_code)
    # and a write, as a joined page sends it
    res = client.post('/api/project/unsaved', base_url=base, json={'unsaved': False},
                      headers={'Origin': base, 'Sec-Fetch-Site': 'same-origin'})
    assert res.status_code == 200
    assert refusals == []


def test_a_script_on_this_computer_still_reads_the_show(client, refusals):
    """No browser headers at all (a script, curl): only the Host is asked."""
    assert client.get('/api/project').status_code == 200
    assert client.get('/api/project', base_url='http://evil.example').status_code == 403


@pytest.mark.parametrize('path', ['/', '/idm-phone', '/output', '/static/js/socket.io.min.js'])
def test_the_pages_and_their_files_open_from_a_link_anywhere(client, refusals, path):
    res = client.get(path, headers={'Sec-Fetch-Site': 'cross-site',
                                    'Referer': FOREIGN_ORIGIN + '/chat'})
    assert res.status_code == 200
    assert refusals == []


def test_a_flood_of_refusals_writes_a_capped_number_of_lines(client, refusals, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(routes_dialog.time, 'monotonic', lambda: clock[0])
    cap = routes_dialog._REFUSAL_LINES
    for _ in range(cap + 15):
        assert client.post('/api/project/new', headers={'Origin': FOREIGN_ORIGIN}).status_code == 403
    assert len(refusals) == cap
    clock[0] += 61
    client.post('/api/project/new', headers={'Origin': FOREIGN_ORIGIN})
    assert len(refusals) == cap + 1
    assert refusals[-1][1]['unlogged_before'] == 15


# ── the socket ───────────────────────────────────────────────────────

def _environ(host, **headers):
    env = {'HTTP_HOST': host, 'wsgi.url_scheme': 'http', 'REMOTE_ADDR': '127.0.0.1',
           'PATH_INFO': '/socket.io/', 'REQUEST_METHOD': 'GET'}
    for k, v in headers.items():
        env['HTTP_' + k.upper()] = v
    return env


def test_the_socket_handshake_takes_only_the_app_s_own_pages(refusals):
    allowed = app_module._socket_origin_allowed
    assert allowed('http://127.0.0.1:8050', _environ('127.0.0.1:8050', origin='http://127.0.0.1:8050'))
    assert allowed(f'http://{LAN}:8050', _environ(f'{LAN}:8050', origin=f'http://{LAN}:8050'))
    assert allowed('http://[::1]:8050', _environ('[::1]:8050', origin='http://[::1]:8050'))
    assert not allowed(FOREIGN_ORIGIN, _environ('127.0.0.1:8050', origin=FOREIGN_ORIGIN))
    assert not allowed('http://127.0.0.1:9', _environ('127.0.0.1:8050', origin='http://127.0.0.1:9'))
    assert not allowed('http://evil.example:8050',
                       _environ('evil.example:8050', origin='http://evil.example:8050'))
    assert [a for a, _ in refusals] == ['socket_rejected_foreign_page'] * 3


def test_a_foreign_socket_connect_hears_nothing_and_a_joined_one_hears_the_show(refusals):
    """The connect itself (a page whose site name was pointed at this
    computer sends no Origin on a polling handshake: the Host gives it
    away), and a joined laptop's connect over the LAN address."""
    sio = app_module.socketio
    foreign = sio.test_client(app_module.app, headers={'Host': 'evil.example:8050'})
    try:
        # refused before the show went out: nothing was ever received
        assert not foreign.is_connected()
        with pytest.raises(RuntimeError):
            foreign.get_received()
    finally:
        if foreign.is_connected():
            foreign.disconnect()
    joined = sio.test_client(app_module.app, headers={
        'Host': f'{LAN}:8050', 'Origin': f'http://{LAN}:8050', 'Sec-Fetch-Site': 'same-origin'})
    try:
        assert joined.is_connected()
        assert 'project_data' in [m['name'] for m in joined.get_received()]
    finally:
        joined.disconnect()
    assert [a for a, _ in refusals] == ['socket_rejected_foreign_page']


# ── real pages in a real browser ─────────────────────────────────────

def _serve(host):
    """The same app at one more address, for the length of this module:
    127.0.0.2 stands in for the LAN address a laptop or phone joins on (an
    address that is neither localhost nor 127.0.0.1, without opening a
    port on the network), and [::1] for the IPv6 loopback."""
    from werkzeug.serving import make_server
    server = make_server(host, 0, app_module.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _bindable(family, host):
    s = socket.socket(family, socket.SOCK_STREAM)
    try:
        s.bind((host, 0))
        return True
    except OSError:
        return False
    finally:
        s.close()


@pytest.fixture(scope='module')
def addresses(e2e_server, server_project_guard):
    port = int(e2e_server.rsplit(':', 1)[1].strip('/'))
    found = {'127.0.0.1': e2e_server.rstrip('/'), 'localhost': f'http://localhost:{port}'}
    servers = []
    if _bindable(socket.AF_INET, '127.0.0.2'):
        s = _serve('127.0.0.2')
        servers.append(s)
        found['lan'] = f'http://127.0.0.2:{s.server_port}'
    if _bindable(socket.AF_INET6, '::1'):
        s = _serve('::1')
        servers.append(s)
        found['[::1]'] = f'http://[::1]:{s.server_port}'
    yield found
    for s in servers:
        s.shutdown()
        s.server_close()


def _context(pw_browser, **kw):
    ctx = pw_browser.new_context(**kw)
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    return ctx


@pytest.mark.parametrize('where', ['127.0.0.1', 'localhost', '[::1]', 'lan'])
def test_the_designer_works_at_every_address(addresses, pw_browser, refusals, where):
    """The desktop window at localhost, 127.0.0.1 and [::1], and a laptop
    joined over the LAN address: the show loads, the socket connects, and
    a rename reaches the server."""
    if where not in addresses:
        pytest.skip(f'{where} cannot be served on this machine')
    base = addresses[where]
    ctx = _context(pw_browser)
    try:
        pg = ctx.new_page()
        errors = []
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(base + '/', wait_until='domcontentloaded')
        pg.wait_for_function("() => window.app && window.app._initialLoadComplete === true"
                             " && window.app.socket && window.app.socket.connected", timeout=20000)
        name = f'RENAMED AT {where}'
        lid = pg.evaluate("""async (name) => {
            const app = window.app, l = app.project.layers[0];
            l.name = name;
            await app.updateLayers([l]);
            await app._layerSavesSettled();
            return l.id;
        }""", name)
        layer = next(l for l in app_module.current_project['layers'] if l['id'] == lid)
        assert layer['name'] == name
        assert refusals == []
        assert errors == []
    finally:
        ctx.close()


def test_the_phone_page_works_over_the_lan_address(addresses, pw_browser, refusals):
    if 'lan' not in addresses:
        pytest.skip('no second address on this machine')
    ctx = _context(pw_browser, viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
    try:
        ph = ctx.new_page()
        ph.goto(addresses['lan'] + '/idm-phone', wait_until='domcontentloaded')
        ph.wait_for_function("() => window.idmPhone && window.idmPhone.S.connected"
                             " && window.idmPhone.app.project", timeout=15000)
        assert refusals == []
    finally:
        ctx.close()


def test_the_output_window_reads_its_feed(addresses, pw_browser, refusals):
    """Output to Display: the window's page and its feed, on this computer."""
    ctx = _context(pw_browser)
    try:
        pg = ctx.new_page()
        statuses = []
        pg.on('response', lambda r: statuses.append(r.status) if '/api/output/feed/' in r.url else None)
        pg.goto(addresses['127.0.0.1'] + '/output?feed=probe', wait_until='domcontentloaded')
        pg.wait_for_function("() => document.readyState === 'complete'")
        pg.wait_for_timeout(1500)
        # the feed it asked for is not open (404): asked, and not refused
        assert statuses and 403 not in statuses, statuses
        assert refusals == []
    finally:
        ctx.close()


def _other_site():
    """Another web page on this computer (any other local web app), on a
    port of its own: a different site to the browser."""
    import http.server

    class Page(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<!doctype html><title>another site</title>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_a_page_from_another_site_can_neither_change_nor_hear_the_show(
        addresses, pw_browser, refusals):
    from conftest import settled
    app_url = addresses['127.0.0.1']
    before = json.dumps(app_module.current_project, sort_keys=True, default=str)
    other = _other_site()
    ctx = _context(pw_browser)
    try:
        pg = ctx.new_page()
        pg.goto(f'http://127.0.0.1:{other.server_address[1]}/', wait_until='domcontentloaded')
        heard = pg.evaluate("""async (app) => {
            const quiet = (p) => p.then(() => 'sent', e => String(e));
            const out = {};
            // File > New, Quit and a file written to disk need no permission
            out.newShow = await quiet(fetch(app + '/api/project/new', { method: 'POST', mode: 'no-cors' }));
            out.quit = await quiet(fetch(app + '/api/app/quit', { method: 'POST', mode: 'no-cors',
                body: JSON.stringify({ discard: true }) }));
            const form = new FormData();
            form.append('path', 'C:/planted.txt');
            form.append('file', new Blob(['x']), 'f.bin');
            out.write = await quiet(fetch(app + '/api/native-dialog/write-file',
                { method: 'POST', mode: 'no-cors', body: form }));
            // and the socket, with the app's own client script
            await new Promise((ok, bad) => {
                const s = document.createElement('script');
                s.src = app + '/static/js/socket.io.min.js';
                s.onload = ok; s.onerror = bad;
                document.head.appendChild(s);
            });
            out.socket = await new Promise((done) => {
                const sock = window.io(app, { reconnection: false, timeout: 5000 });
                sock.on('project_data', () => { done('heard the show'); sock.close(); });
                sock.on('connect_error', () => { done('refused'); sock.close(); });
                setTimeout(() => done('timeout'), 8000);
            });
            return out;
        }""", app_url)
        assert heard['socket'] == 'refused', heard
        lines = settled(pg, lambda: [d for a, d in refusals if a == 'request_rejected_foreign_page'],
                        lambda found: len(found) >= 3)
        assert {d['path'] for d in lines} >= {'/api/project/new', '/api/app/quit',
                                              '/api/native-dialog/write-file'}, lines
        assert 'socket_rejected_foreign_page' in [a for a, _ in refusals]
        assert json.dumps(app_module.current_project, sort_keys=True, default=str) == before
    finally:
        ctx.close()
        other.shutdown()
        other.server_close()
