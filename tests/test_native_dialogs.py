"""Tests for native dialog API endpoints with mocked OS interactions."""

import os
import base64
import tempfile
from unittest.mock import patch


# ── Save file dialog ──────────────────────────────────────────────────

def test_save_file_dialog_returns_path(client):
    """Native save dialog returns selected file path."""
    with patch('app._native_choose_save_file', return_value='/tmp/test_output.png'):
        resp = client.post('/api/native-dialog/save-file', json={
            'suggested_name': 'export.png',
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert data['path'] == '/tmp/test_output.png'


def test_save_file_dialog_cancelled(client):
    """Native save dialog returns cancelled when user cancels."""
    with patch('app._native_choose_save_file', return_value=None):
        resp = client.post('/api/native-dialog/save-file', json={
            'suggested_name': 'export.png',
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is False
    assert data['cancelled'] is True


def test_save_file_dialog_default_name(client):
    """Save dialog uses default name when none provided."""
    with patch('app._native_choose_save_file', return_value='/tmp/output.bin') as mock:
        resp = client.post('/api/native-dialog/save-file', json={})
    assert resp.status_code == 200
    mock.assert_called_once_with('output.bin')


def test_save_file_dialog_error(client):
    """Save dialog returns 500 on OS error."""
    with patch('app._native_choose_save_file', side_effect=OSError('Dialog failed')):
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
    with patch('app._native_choose_directory', return_value='/home/user/exports'):
        resp = client.post('/api/native-dialog/select-directory')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert data['path'] == '/home/user/exports'


def test_select_directory_cancelled(client):
    """Directory picker returns cancelled when user cancels."""
    with patch('app._native_choose_directory', return_value=None):
        resp = client.post('/api/native-dialog/select-directory')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is False
    assert data['cancelled'] is True


def test_select_directory_error(client):
    """Directory picker returns 500 on OS error."""
    with patch('app._native_choose_directory', side_effect=OSError('No display')):
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
