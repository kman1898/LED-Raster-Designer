"""Tests for the in-app log viewer API (/api/logs), mainly the optional
`since` / `until` epoch-ms time filter used by Help -> Show Logs."""

import json
from datetime import datetime, timedelta

import pytest

import routes_logs


def _epoch_ms(dt):
    """Epoch ms for a naive LOCAL datetime, matching how log lines are read."""
    return int(dt.timestamp() * 1000)


def _log_line(dt, action='test_action'):
    """One log line in the real on-disk shape: outer local timestamp plus a
    details.clientTime in UTC that the filter must ignore."""
    return json.dumps({
        'timestamp': dt.strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'client',
        'action': action,
        'details': {'clientTime': '2000-01-01T00:00:00.000Z'}
    })


@pytest.fixture()
def log_file(tmp_path, monkeypatch):
    """Point the logs blueprint at a throwaway log file and return its path."""
    path = tmp_path / 'led_raster_designer.log'
    path.write_text('', encoding='utf-8')
    monkeypatch.setattr(routes_logs, 'LOG_FILE_PATH', str(path))
    monkeypatch.setattr(routes_logs, 'LOG_DIR_PATH', str(tmp_path))
    return path


def _write_lines(path, lines):
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


BASE = datetime(2026, 7, 25, 20, 0, 0)


def test_logs_no_filter_returns_everything(client, log_file):
    _write_lines(log_file, [_log_line(BASE + timedelta(minutes=i)) for i in range(5)])
    data = client.get('/api/logs').get_json()
    assert len(data['lines']) == 5
    assert data['filtered'] is False
    assert data['matched_count'] is None


def test_logs_since_filters_out_older_lines(client, log_file):
    _write_lines(log_file, [_log_line(BASE + timedelta(minutes=i)) for i in range(5)])
    since = _epoch_ms(BASE + timedelta(minutes=3))
    data = client.get(f'/api/logs?since={since}').get_json()
    assert len(data['lines']) == 2
    assert data['filtered'] is True
    assert data['matched_count'] == 2
    assert '20:03:00' in data['lines'][0]
    assert '20:04:00' in data['lines'][1]


def test_logs_until_is_inclusive(client, log_file):
    _write_lines(log_file, [_log_line(BASE + timedelta(minutes=i)) for i in range(5)])
    until = _epoch_ms(BASE + timedelta(minutes=2))
    data = client.get(f'/api/logs?until={until}').get_json()
    # 20:00, 20:01 and the 20:02 line the user asked "to"
    assert len(data['lines']) == 3
    assert '20:02:00' in data['lines'][-1]


def test_logs_since_and_until_window(client, log_file):
    _write_lines(log_file, [_log_line(BASE + timedelta(minutes=i)) for i in range(10)])
    since = _epoch_ms(BASE + timedelta(minutes=4))
    until = _epoch_ms(BASE + timedelta(minutes=6))
    data = client.get(f'/api/logs?since={since}&until={until}').get_json()
    assert len(data['lines']) == 3
    assert data['matched_count'] == 3


def test_logs_filter_searches_whole_file_not_just_tail(client, log_file):
    # 300 lines: a "From: 1d ago" style window must reach past the tail the
    # unfiltered request would have returned.
    _write_lines(log_file, [_log_line(BASE + timedelta(minutes=i)) for i in range(300)])
    since = _epoch_ms(BASE)
    until = _epoch_ms(BASE + timedelta(minutes=9))
    data = client.get(f'/api/logs?since={since}&until={until}').get_json()
    assert data['matched_count'] == 10
    assert len(data['lines']) == 10
    assert '20:00:00' in data['lines'][0]


def test_logs_lines_cap_applied_after_filtering(client, log_file):
    _write_lines(log_file, [_log_line(BASE + timedelta(minutes=i)) for i in range(120)])
    since = _epoch_ms(BASE)
    # 50 is the smallest cap the endpoint honours
    data = client.get(f'/api/logs?since={since}&lines=50').get_json()
    assert data['matched_count'] == 120   # everything matched
    assert len(data['lines']) == 50       # ...but only the most recent 50 came back
    assert data['returned_count'] == 50
    assert '21:59:00' in data['lines'][-1]


def test_logs_non_numeric_filter_params_are_ignored(client, log_file):
    _write_lines(log_file, [_log_line(BASE + timedelta(minutes=i)) for i in range(5)])
    resp = client.get('/api/logs?since=notanumber&until=')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['lines']) == 5
    assert data['filtered'] is False


def test_logs_filter_drops_lines_without_a_timestamp(client, log_file):
    _write_lines(log_file, [
        'not json at all',
        '{"source": "server", "action": "no_timestamp_here"}',
        _log_line(BASE),
    ])
    since = _epoch_ms(BASE - timedelta(hours=1))
    data = client.get(f'/api/logs?since={since}').get_json()
    assert data['lines'] == [_log_line(BASE)]
    assert data['matched_count'] == 1
    # Unfiltered, the junk lines are still shown verbatim
    assert len(client.get('/api/logs').get_json()['lines']) == 3


def test_logs_filter_ignores_details_client_time(client, log_file):
    # details.clientTime is UTC and years away from the outer timestamp; the
    # filter must key off the outer (local) timestamp only.
    _write_lines(log_file, [_log_line(BASE)])
    since = _epoch_ms(BASE - timedelta(minutes=1))
    until = _epoch_ms(BASE + timedelta(minutes=1))
    data = client.get(f'/api/logs?since={since}&until={until}').get_json()
    assert data['matched_count'] == 1


def test_logs_filter_on_missing_file_is_empty_not_error(client, tmp_path, monkeypatch):
    monkeypatch.setattr(routes_logs, 'LOG_FILE_PATH',
                        str(tmp_path / 'does_not_exist.log'))
    monkeypatch.setattr(routes_logs, 'LOG_DIR_PATH', str(tmp_path))
    resp = client.get(f'/api/logs?since={_epoch_ms(BASE)}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['lines'] == []
    assert data['file_size_bytes'] == 0


def test_log_line_epoch_ms_helper():
    line = _log_line(BASE)
    assert routes_logs._log_line_epoch_ms(line) == _epoch_ms(BASE)
    assert routes_logs._log_line_epoch_ms('{"action": "x"}') is None
    assert routes_logs._log_line_epoch_ms('{"timestamp": "not-a-date"}') is None
