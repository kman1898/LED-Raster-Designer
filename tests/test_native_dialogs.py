"""Tests for native dialog API endpoints with mocked OS interactions.

v0.11.0: the dialog helpers now return (path, status) rather than a bare path.
status is 'ok', 'cancelled' (the user dismissed the dialog) or 'unavailable'
(it could not be opened at all). Conflating the last two is what made a failed
Windows folder chooser - and a deliberate Cancel - both dump the export into
the browser's downloads folder. See tests/test_native_dialog.py for the
helper-level contract; this file covers the routes.
"""

import os
import base64
import tempfile
from unittest.mock import patch


# ── Save file dialog ──────────────────────────────────────────────────

def test_save_file_dialog_returns_path(client):
    """Native save dialog returns selected file path."""
    with patch('routes_dialog._native_choose_save_file',
               return_value=('/tmp/test_output.png', 'ok')):
        resp = client.post('/api/native-dialog/save-file', json={
            'suggested_name': 'export.png',
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert data['path'] == '/tmp/test_output.png'


def test_save_file_dialog_cancelled(client):
    """Native save dialog returns cancelled when user cancels."""
    with patch('routes_dialog._native_choose_save_file', return_value=(None, 'cancelled')):
        resp = client.post('/api/native-dialog/save-file', json={
            'suggested_name': 'export.png',
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is False
    assert data['cancelled'] is True


def test_save_file_dialog_default_name(client):
    """Save dialog uses default name when none provided."""
    with patch('routes_dialog._native_choose_save_file',
               return_value=('/tmp/output.bin', 'ok')) as mock:
        resp = client.post('/api/native-dialog/save-file', json={})
    assert resp.status_code == 200
    mock.assert_called_once_with('output.bin')


def test_save_file_dialog_error(client):
    """Save dialog returns 500 on OS error."""
    with patch('routes_dialog._native_choose_save_file', side_effect=OSError('Dialog failed')):
        resp = client.post('/api/native-dialog/save-file', json={
            'suggested_name': 'test.png',
        })
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['ok'] is False
    assert 'Dialog failed' in data['error']


# ── Select directory dialog ──────────────────────────────────────────

def test_select_directory_returns_path(client):
    """Directory picker returns selected path."""
    with patch('routes_dialog._native_choose_directory',
               return_value=('/home/user/exports', 'ok')):
        resp = client.post('/api/native-dialog/select-directory')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert data['path'] == '/home/user/exports'


def test_select_directory_cancelled(client):
    """Directory picker returns cancelled when user cancels."""
    with patch('routes_dialog._native_choose_directory', return_value=(None, 'cancelled')):
        resp = client.post('/api/native-dialog/select-directory')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is False
    assert data['cancelled'] is True


def test_select_directory_unavailable_is_not_reported_as_a_cancel(client):
    """A dialog that could not open must NOT read as the user cancelling.

    The client aborts on a cancel and falls back to a browser download on
    unavailable. Swap them and either the export is lost, or Cancel saves the
    files anyway - which is the bug this release fixes.
    """
    with patch('routes_dialog._native_choose_directory', return_value=(None, 'unavailable')):
        resp = client.post('/api/native-dialog/select-directory')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is False
    assert data['cancelled'] is False
    assert data['unavailable'] is True


def test_select_directory_error(client):
    """Directory picker returns 500 on OS error."""
    with patch('routes_dialog._native_choose_directory', side_effect=OSError('No display')):
        resp = client.post('/api/native-dialog/select-directory')
    assert resp.status_code == 500
    assert resp.get_json()['ok'] is False


# ── Write file ────────────────────────────────────────────────────────

def test_write_file_creates_file(client):
    """Write file endpoint decodes base64 and writes to disk."""
    content = b'Hello, LED!'
    b64 = base64.b64encode(content).decode()
    data_url = f'data:application/octet-stream;base64,{b64}'

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, 'output.bin')
        resp = client.post('/api/native-dialog/write-file', json={
            'path': file_path,
            'data_url': data_url,
        })
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        with open(file_path, 'rb') as f:
            assert f.read() == content


def test_write_file_creates_directories(client):
    """Write file creates parent directories if needed."""
    content = b'nested write'
    b64 = base64.b64encode(content).decode()

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, 'deep', 'nested', 'output.bin')
        resp = client.post('/api/native-dialog/write-file', json={
            'path': file_path,
            'data_url': f'data:application/octet-stream;base64,{b64}',
        })
        assert resp.status_code == 200
        assert os.path.exists(file_path)


def test_write_file_missing_path(client):
    """Write file returns 400 when path is missing."""
    resp = client.post('/api/native-dialog/write-file', json={
        'data_url': 'data:application/octet-stream;base64,aGVsbG8=',
    })
    assert resp.status_code == 400


def test_write_file_missing_data(client):
    """Write file returns 400 when data_url is missing."""
    resp = client.post('/api/native-dialog/write-file', json={
        'path': '/tmp/test.bin',
    })
    assert resp.status_code == 400


# ── Write multiple files ──────────────────────────────────────────────

def test_write_multiple_files(client):
    """Write multiple files to a directory."""
    b64_1 = base64.b64encode(b'file one').decode()
    b64_2 = base64.b64encode(b'file two').decode()

    with tempfile.TemporaryDirectory() as tmpdir:
        resp = client.post('/api/native-dialog/write-multiple', json={
            'directory': tmpdir,
            'files': [
                {'filename': 'a.bin', 'data_url': f'data:application/octet-stream;base64,{b64_1}'},
                {'filename': 'b.bin', 'data_url': f'data:application/octet-stream;base64,{b64_2}'},
            ],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['written'] == 2
        assert os.path.exists(os.path.join(tmpdir, 'a.bin'))
        assert os.path.exists(os.path.join(tmpdir, 'b.bin'))


def test_write_multiple_skips_incomplete(client):
    """Files missing filename or data_url are skipped."""
    b64 = base64.b64encode(b'good file').decode()

    with tempfile.TemporaryDirectory() as tmpdir:
        resp = client.post('/api/native-dialog/write-multiple', json={
            'directory': tmpdir,
            'files': [
                {'filename': 'good.bin', 'data_url': f'data:application/octet-stream;base64,{b64}'},
                {'filename': '', 'data_url': f'data:application/octet-stream;base64,{b64}'},
                {'filename': 'no_data.bin'},
            ],
        })
        assert resp.status_code == 200
        assert resp.get_json()['written'] == 1


def test_write_multiple_missing_directory(client):
    """Write multiple returns 400 when directory is missing."""
    resp = client.post('/api/native-dialog/write-multiple', json={
        'files': [{'filename': 'a.bin', 'data_url': 'data:;base64,aGk='}],
    })
    assert resp.status_code == 400


def test_write_multiple_path_traversal_safety(client):
    """Filenames with path traversal are sanitized via os.path.basename."""
    b64 = base64.b64encode(b'safe data').decode()

    with tempfile.TemporaryDirectory() as tmpdir:
        resp = client.post('/api/native-dialog/write-multiple', json={
            'directory': tmpdir,
            'files': [
                {'filename': '../../../etc/passwd', 'data_url': f'data:application/octet-stream;base64,{b64}'},
            ],
        })
        assert resp.status_code == 200
        # Should write as 'passwd' in the target dir, not escape
        assert os.path.exists(os.path.join(tmpdir, 'passwd'))
        assert not os.path.exists('/etc/passwd_test')


# ── Loopback-only enforcement ────────────────────────────────────────────
# The native-dialog endpoints open dialogs on / write files to the HOST
# machine; a remote LAN client must get a 403 (its saves belong on the
# remote machine via browser download).

def test_native_dialogs_reject_remote_clients(client, monkeypatch):
    import routes_dialog as _rd
    # Pin the trusted set so this cannot depend on the developer's LAN.
    monkeypatch.setattr(_rd, '_own_addresses', lambda: {'127.0.0.1', '::1'})
    for path in ('/api/native-dialog/save-file',
                 '/api/native-dialog/select-directory',
                 '/api/native-dialog/write-file',
                 '/api/native-dialog/write-multiple'):
        resp = client.post(path, json={},
                           environ_overrides={'REMOTE_ADDR': '192.168.1.50'})
        assert resp.status_code == 403, f'{path} not blocked for remote client'
        assert resp.get_json()['ok'] is False


def test_native_dialogs_allow_loopback(client):
    # Loopback still reaches the handlers (400 = handler ran and validated
    # the empty payload, NOT a 403 rejection).
    resp = client.post('/api/native-dialog/write-file', json={},
                       environ_overrides={'REMOTE_ADDR': '127.0.0.1'})
    assert resp.status_code == 400


def test_logs_reveal_rejects_remote_clients(client):
    resp = client.post('/api/logs/reveal',
                       environ_overrides={'REMOTE_ADDR': '10.0.0.9'})
    assert resp.status_code == 403
