"""Who may read and write the app log.

The app listens on the network for the IDM phone page, and the log holds
the show's contacts, file paths and addresses. Reading it is for the
computer running the app only (like Clear and Open Folder); writing is for
the app's own pages, a capped size and rate per machine. A refused event is
counted, never written.
"""
import json

import pytest

import routes_logs

REMOTE = {'REMOTE_ADDR': '203.0.113.40'}   # a documentation address, never this machine's
HOST = 'localhost'                          # the test client's Host


@pytest.fixture()
def log_file(tmp_path, monkeypatch):
    path = tmp_path / 'led_raster_designer.log'
    path.write_text('{"timestamp": "2026-11-18 10:00:00", "action": "secret_line"}\n',
                    encoding='utf-8')
    monkeypatch.setattr(routes_logs, 'LOG_FILE_PATH', str(path))
    monkeypatch.setattr(routes_logs, 'LOG_DIR_PATH', str(tmp_path))
    return path


@pytest.fixture()
def written(monkeypatch):
    """Every line the log routes write, instead of the real log file; and a
    fresh flood counter for each test."""
    lines = []

    def spy(action, details=None, source='server'):
        lines.append((action, details, source))

    import routes_dialog
    monkeypatch.setattr(routes_logs, 'log_event', spy)
    monkeypatch.setattr(routes_logs, '_clients', {})
    # refusals of pages from other sites (app.py refuse_foreign_pages)
    monkeypatch.setattr(routes_dialog, 'log_event', spy)
    monkeypatch.setattr(routes_dialog, '_refusals', {})
    return lines


def _post(client, body, environ=None, headers=None, raw=None):
    data = raw if raw is not None else json.dumps(body)
    return client.post('/api/log', data=data, content_type='application/json',
                       headers=headers or {}, environ_overrides=environ or {})


def _client_lines(written):
    return [w for w in written if w[2] == 'client']


# ── reading ─────────────────────────────────────────────────────────

def test_another_machine_cannot_read_the_log(client, log_file, written):
    res = client.get('/api/logs', environ_overrides=REMOTE)
    assert res.status_code == 403
    assert 'secret_line' not in res.get_data(as_text=True)
    filtered = client.get('/api/logs?since=0', environ_overrides=REMOTE)
    assert filtered.status_code == 403


def test_the_computer_running_the_app_reads_the_log(client, log_file, written):
    res = client.get('/api/logs')
    assert res.status_code == 200
    assert any('secret_line' in line for line in res.get_json()['lines'])


# ── writing ─────────────────────────────────────────────────────────

def test_a_page_from_another_site_cannot_write(client, written):
    res = _post(client, {'action': 'forged', 'details': {'x': 1}},
                environ=REMOTE, headers={'Origin': 'http://evil.example'})
    assert res.status_code == 403
    res = _post(client, {'action': 'forged'}, environ=REMOTE,
                headers={'Referer': 'http://evil.example/page'})
    assert res.status_code == 403
    # another machine with no page behind it at all
    assert _post(client, {'action': 'forged'}, environ=REMOTE).status_code == 403
    # the same host name on another port is another site
    assert _post(client, {'action': 'forged'}, environ=REMOTE,
                 headers={'Origin': f'http://{HOST}:9'}).status_code == 403
    assert _client_lines(written) == []


def test_an_oversized_event_is_refused(client, written):
    big = {'action': 'huge', 'details': {'blob': 'x' * (routes_logs._MAX_EVENT_BYTES + 10)}}
    res = _post(client, big, environ=REMOTE, headers={'Origin': f'http://{HOST}'})
    assert res.status_code == 413
    res = _post(client, big)   # the host's own oversized event too
    assert res.status_code == 413
    assert _client_lines(written) == []


def test_the_phone_page_logs(client, written):
    """A phone on the LAN, on the IDM phone page the app served."""
    res = _post(client, {'action': 'phone_event', 'details': {'step': 3}}, environ=REMOTE,
                headers={'Origin': f'http://{HOST}',
                         'Referer': f'http://{HOST}/idm-phone'})
    assert res.status_code == 200
    # a browser that sends only the Referer
    res = _post(client, {'action': 'phone_event_2'}, environ=REMOTE,
                headers={'Referer': f'http://{HOST}/idm-phone'})
    assert res.status_code == 200
    actions = [w[0] for w in _client_lines(written)]
    assert actions == ['phone_event', 'phone_event_2']


def test_a_joined_tablet_logs_from_the_app_page(client, written):
    res = _post(client, {'action': 'tablet_event'}, environ=REMOTE,
                headers={'Origin': f'http://{HOST}', 'Referer': f'http://{HOST}/'})
    assert res.status_code == 200
    assert [w[0] for w in _client_lines(written)] == ['tablet_event']


def test_a_flood_is_dropped_and_counted_in_one_warning(client, written, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(routes_logs.time, 'monotonic', lambda: clock[0])
    ours = {'Origin': f'http://{HOST}'}
    burst = int(routes_logs._EVENT_BURST)
    total = burst + 250
    codes = [_post(client, {'action': 'spam', 'details': {'n': i}}, environ=REMOTE,
                   headers=ours).status_code for i in range(total)]
    assert codes[:burst] == [200] * burst
    assert set(codes[burst:]) == {429}
    assert len(_client_lines(written)) == burst
    assert not [w for w in written if w[0] == 'client_log_dropped']
    # a second on: 50 more are taken, and the drops are reported once
    clock[0] += 1.0
    assert _post(client, {'action': 'after'}, environ=REMOTE, headers=ours).status_code == 200
    warns = [w for w in written if w[0] == 'client_log_dropped']
    assert len(warns) == 1
    assert warns[0][1]['dropped'] == total - burst
    assert warns[0][1]['remote_addr'] == REMOTE['REMOTE_ADDR']
    # the dropped payloads are not in it
    assert 'spam' not in json.dumps(warns[0][1])


def test_refused_payloads_are_never_written(client, written, monkeypatch):
    clock = [5000.0]
    monkeypatch.setattr(routes_logs.time, 'monotonic', lambda: clock[0])
    _post(client, {'action': 'forged', 'details': {'phone': '555-0100'}}, environ=REMOTE,
          headers={'Origin': 'http://evil.example'})
    clock[0] += 2.0
    _post(client, {'action': 'ok'})
    text = json.dumps(written)
    assert '555-0100' not in text and 'forged' not in text
    warns = [w for w in written if w[0] == 'client_log_dropped']
    assert len(warns) == 1 and warns[0][1]['refused'] == 1


@pytest.mark.parametrize('path', ['/idm-phone', '/'])
def test_a_real_page_still_logs(e2e_server, server_project_guard, pw_browser, written, path):
    """The phone page and the app page, in a browser, by beacon and by
    fetch: the Origin the browser sends is the app's own."""
    from conftest import settled
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    try:
        pg = context.new_page()
        pg.goto(e2e_server.rstrip('/') + path, wait_until='domcontentloaded')
        status = pg.evaluate("""async () => {
            const body = (a) => JSON.stringify({ action: a, details: { n: 1 } });
            navigator.sendBeacon('/api/log', new Blob([body('probe_beacon')], { type: 'application/json' }));
            const r = await fetch('/api/log', { method: 'POST',
                headers: { 'Content-Type': 'application/json' }, body: body('probe_fetch') });
            return r.status;
        }""")
        assert status == 200
        settled(pg, lambda: {w[0] for w in _client_lines(written)},
                lambda seen: {'probe_beacon', 'probe_fetch'} <= seen)
    finally:
        context.close()


def test_the_host_is_not_rate_limited(client, written):
    """The app's own windows burst past 100 a second while a show opens."""
    n = int(routes_logs._EVENT_BURST) + 50
    codes = {_post(client, {'action': 'burst'}).status_code for _ in range(n)}
    assert codes == {200}
    assert len(_client_lines(written)) == n


# ── pages from other sites, on this computer ────────────────────────
# A page on any other site, open in a browser on the computer running the
# app, reaches the app at localhost from this computer's own address, so
# the address alone lets it through. What the browser says sent the
# request (Origin, Sec-Fetch-Site, Referer) and the Host it names refuse it.

LAN = '192.168.1.20'                    # the LAN address a phone joins on
PHONE = {'REMOTE_ADDR': '192.168.1.77'}


def _spy_folder_window(monkeypatch):
    """Open Folder never opens a real window from a test, refused or not."""
    opened = []
    monkeypatch.setattr(routes_logs.subprocess, 'Popen', lambda *a, **k: opened.append(a))
    if hasattr(routes_logs.os, 'startfile'):
        monkeypatch.setattr(routes_logs.os, 'startfile', lambda *a, **k: opened.append(a))
    return opened


@pytest.fixture()
def no_folder_window(monkeypatch):
    return _spy_folder_window(monkeypatch)


FOREIGN = [
    pytest.param({'Origin': 'http://evil.example'}, 'http://localhost', id='other-site-origin'),
    pytest.param({'Origin': 'http://localhost:9'}, 'http://localhost', id='other-port-origin'),
    pytest.param({'Origin': 'null'}, 'http://localhost', id='null-origin'),
    pytest.param({'Referer': 'http://evil.example/page'}, 'http://localhost', id='other-site-referer'),
    pytest.param({'Sec-Fetch-Site': 'cross-site'}, 'http://localhost', id='cross-site-fetch'),
    pytest.param({'Sec-Fetch-Site': 'same-site', 'Origin': 'http://localhost'},
                 'http://localhost', id='same-site-fetch'),
    # a site's name pointed at this computer after its page loaded: the
    # browser sends that site's own name as both Host and Origin
    pytest.param({'Origin': 'http://evil.example:8050'}, 'http://evil.example:8050',
                 id='rebound-name'),
    pytest.param({}, 'http://evil.example:8050', id='rebound-name-no-origin'),
]


@pytest.mark.parametrize('headers,base', FOREIGN)
def test_a_page_from_another_site_on_this_computer_is_refused(
        client, log_file, written, no_folder_window, headers, base):
    res = client.get('/api/logs', base_url=base, headers=headers)
    assert res.status_code == 403
    assert 'secret_line' not in res.get_data(as_text=True)
    assert client.delete('/api/logs', base_url=base, headers=headers).status_code == 403
    assert 'secret_line' in log_file.read_text(encoding='utf-8')
    assert client.post('/api/logs/reveal', base_url=base, headers=headers).status_code == 403
    assert no_folder_window == []
    res = client.post('/api/log', base_url=base, headers=headers,
                      data=json.dumps({'action': 'forged'}), content_type='text/plain')
    assert res.status_code == 403
    assert _client_lines(written) == []
    refused = [w for w in written if w[0] == 'request_rejected_foreign_page']
    assert len(refused) == 3
    assert {r[1]['path'] for r in refused} == {'/api/logs', '/api/logs/reveal'}


@pytest.mark.parametrize('base', ['http://localhost:8050', 'http://127.0.0.1:8050',
                                  'http://[::1]:8050', f'http://{LAN}:8050'])
def test_the_app_window_uses_its_log_at_every_address_it_is_opened_at(
        client, log_file, written, no_folder_window, monkeypatch, base):
    """The designer on this computer, opened at localhost, 127.0.0.1, [::1]
    or the LAN address the launcher bound it to."""
    import routes_dialog
    monkeypatch.setattr(routes_dialog, '_own_addresses',
                        lambda: {'127.0.0.1', '::1', LAN, '::ffff:' + LAN})
    own = {'Origin': base, 'Referer': base + '/', 'Sec-Fetch-Site': 'same-origin'}
    me = {'REMOTE_ADDR': LAN if LAN in base else '127.0.0.1'}
    viewer = {'Referer': base + '/', 'Sec-Fetch-Site': 'same-origin'}   # a GET sends no Origin
    res = client.get('/api/logs', base_url=base, headers=viewer, environ_overrides=me)
    assert res.status_code == 200
    assert any('secret_line' in line for line in res.get_json()['lines'])
    assert client.post('/api/logs/reveal', base_url=base, headers=own,
                       environ_overrides=me).status_code == 200
    assert len(no_folder_window) == 1
    assert client.post('/api/log', base_url=base, headers=own, environ_overrides=me,
                       data=json.dumps({'action': 'window_event'}),
                       content_type='application/json').status_code == 200
    assert client.delete('/api/logs', base_url=base, headers=own,
                         environ_overrides=me).status_code == 200
    assert [w[0] for w in _client_lines(written)] == ['window_event']


def test_the_phone_page_joined_over_the_lan_logs_and_still_cannot_read(
        client, log_file, written):
    base = f'http://{LAN}:8050'
    page = {'Origin': base, 'Referer': base + '/idm-phone', 'Sec-Fetch-Site': 'same-origin'}
    res = client.post('/api/log', base_url=base, headers=page, environ_overrides=PHONE,
                      data=json.dumps({'action': 'phone_lan_event'}),
                      content_type='application/json')
    assert res.status_code == 200
    # a beacon from a browser that sends only the Referer
    res = client.post('/api/log', base_url=base, environ_overrides=PHONE,
                      headers={'Referer': base + '/idm-phone'},
                      data=json.dumps({'action': 'phone_lan_beacon'}),
                      content_type='application/json')
    assert res.status_code == 200
    assert [w[0] for w in _client_lines(written)] == ['phone_lan_event', 'phone_lan_beacon']
    # reading stays for the computer running the app
    res = client.get('/api/logs', base_url=base, environ_overrides=PHONE,
                     headers={'Referer': base + '/idm-phone'})
    assert res.status_code == 403


def _other_site():
    """Another web page served on this computer (any other local web app),
    on a port of its own: a different site to the browser."""
    import http.server
    import threading

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


def test_a_real_page_from_another_site_cannot_reach_the_log(
        e2e_server, server_project_guard, pw_browser, written, monkeypatch):
    """A page on another site open in a browser on this computer: the
    browser's own headers, not ones a test wrote. Its posts need no
    permission from the app (no-cors, a beacon), so they reach the server
    and must be refused there."""
    from conftest import settled
    opened = _spy_folder_window(monkeypatch)
    app_url = e2e_server.rstrip('/')
    other = _other_site()
    context = pw_browser.new_context()
    try:
        pg = context.new_page()
        pg.goto(f'http://127.0.0.1:{other.server_address[1]}/', wait_until='domcontentloaded')
        sent = pg.evaluate("""async (app) => {
            const body = JSON.stringify({ action: 'forged_from_page', details: {} });
            const out = [navigator.sendBeacon(app + '/api/log', new Blob([body], { type: 'text/plain' }))];
            const quiet = (p) => p.then(r => out.push(r.type), e => out.push(String(e)));
            await quiet(fetch(app + '/api/log', { method: 'POST', mode: 'no-cors', body }));
            await quiet(fetch(app + '/api/logs/reveal', { method: 'POST', mode: 'no-cors' }));
            await quiet(fetch(app + '/api/logs', { mode: 'no-cors' }));
            return out;
        }""", app_url)

        def seen():
            refused_writes = sum(st['refused'] for st in routes_logs._clients.values())
            lines = [w for w in written if w[0] == 'request_rejected_foreign_page']
            return refused_writes, lines
        refused_writes, refused = settled(pg, seen, lambda s: s[0] >= 2 and len(s[1]) >= 2)
        # the beacon and the post both reached the server and were refused
        assert refused_writes == 2, (sent, refused)
        assert {r[1]['path'] for r in refused} == {'/api/logs', '/api/logs/reveal'}
        # the browser itself named the sending page as another site
        assert {r[1]['reason'] for r in refused} <= {'cross-site', 'origin', 'referer'}
        assert opened == []
        assert _client_lines(written) == []
    finally:
        context.close()
        other.shutdown()
        other.server_close()
