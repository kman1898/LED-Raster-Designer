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

    monkeypatch.setattr(routes_logs, 'log_event', spy)
    monkeypatch.setattr(routes_logs, '_clients', {})
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
    codes = [_post(client, {'action': 'spam', 'details': {'n': i}}, environ=REMOTE,
                   headers=ours).status_code for i in range(400)]
    burst = int(routes_logs._EVENT_BURST)
    assert codes[:burst] == [200] * burst
    assert set(codes[burst:]) == {429}
    assert len(_client_lines(written)) == burst
    assert not [w for w in written if w[0] == 'client_log_dropped']
    # a second on: 50 more are taken, and the drops are reported once
    clock[0] += 1.0
    assert _post(client, {'action': 'after'}, environ=REMOTE, headers=ours).status_code == 200
    warns = [w for w in written if w[0] == 'client_log_dropped']
    assert len(warns) == 1
    assert warns[0][1]['dropped'] == 400 - burst
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
