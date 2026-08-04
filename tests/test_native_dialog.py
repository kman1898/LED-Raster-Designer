"""Native folder/save dialogs, and the cancel-vs-unavailable split.

Reported on Windows: "the export button just dumps the files to downloads, i
need it to open a window and let me choose the folder."

The folder chooser was already implemented. On localhost the app deliberately
skips the browser's own File System Access API - Chrome revokes the user
gesture while the canvases render, and the export lands zero files - and asks
the SERVER to open a native dialog on the host instead. On Windows that is
PowerShell driving FolderBrowserDialog.

Two things made that fail silently:

* WinForms dialogs need a single-threaded apartment, and with no owner window
  the dialog can open BEHIND the browser where nobody sees it. Now launched
  with -STA and given a TopMost owner.
* _run_dialog_command returned a bare None for BOTH "user cancelled" and "the
  dialog could not open", and the caller treated both as "fall back to a
  browser download". So pressing Cancel still dumped every file into Downloads,
  and a genuine failure gave no clue anywhere. It now reports which happened.

The Windows branch cannot be executed here, so it is asserted structurally -
the flags and calls that make it work have to be present in the command.
"""

import sys
import os
import subprocess

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import app  # noqa: F401,E402  (registers the blueprint; routes_dialog imports it)
import routes_dialog as rd  # noqa: E402


# ── the three outcomes are told apart ─────────────────────────────────────

def test_a_missing_helper_is_unavailable_not_a_cancel():
    path, status = rd._run_dialog_command(['no-such-binary-xyz-123'], 'probe')
    assert path is None
    assert status == 'unavailable'


def test_a_failing_helper_is_unavailable_not_a_cancel():
    path, status = rd._run_dialog_command(
        ['sh', '-c', 'echo boom >&2; exit 3'], 'probe')
    assert path is None
    assert status == 'unavailable'


def test_exit_zero_with_no_path_is_a_user_cancel():
    """The user dismissed the dialog. Nothing should be written anywhere."""
    path, status = rd._run_dialog_command(['sh', '-c', 'exit 0'], 'probe')
    assert path is None
    assert status == 'cancelled'


def test_a_chosen_path_comes_back_ok():
    path, status = rd._run_dialog_command(
        ['sh', '-c', 'echo /tmp/somewhere'], 'probe')
    assert path == '/tmp/somewhere'
    assert status == 'ok'


# ── the routes pass that distinction to the client ────────────────────────

@pytest.fixture
def client():
    app.app.config['TESTING'] = True
    with app.app.test_client() as c:
        yield c


def test_select_directory_reports_a_cancel_as_a_cancel(client, monkeypatch):
    monkeypatch.setattr(rd, '_native_choose_directory', lambda: (None, 'cancelled'))
    body = client.post('/api/native-dialog/select-directory').get_json()
    assert body['ok'] is False
    assert body['cancelled'] is True
    assert body['unavailable'] is False


def test_select_directory_reports_an_unopenable_dialog_as_unavailable(client, monkeypatch):
    monkeypatch.setattr(rd, '_native_choose_directory', lambda: (None, 'unavailable'))
    body = client.post('/api/native-dialog/select-directory').get_json()
    assert body['ok'] is False
    assert body['cancelled'] is False, (
        'a dialog that failed to open must not read as the user cancelling - '
        'the client would then save nothing at all')
    assert body['unavailable'] is True


def test_select_directory_returns_the_chosen_folder(client, monkeypatch):
    monkeypatch.setattr(rd, '_native_choose_directory',
                        lambda: ('/Users/someone/Desktop/Show', 'ok'))
    body = client.post('/api/native-dialog/select-directory').get_json()
    assert body == {'ok': True, 'path': '/Users/someone/Desktop/Show'}


def test_save_file_reports_the_same_three_outcomes(client, monkeypatch):
    monkeypatch.setattr(rd, '_native_choose_save_file', lambda n: (None, 'cancelled'))
    body = client.post('/api/native-dialog/save-file', json={}).get_json()
    assert (body['cancelled'], body['unavailable']) == (True, False)

    monkeypatch.setattr(rd, '_native_choose_save_file', lambda n: (None, 'unavailable'))
    body = client.post('/api/native-dialog/save-file', json={}).get_json()
    assert (body['cancelled'], body['unavailable']) == (False, True)

    monkeypatch.setattr(rd, '_native_choose_save_file', lambda n: ('/tmp/x.psd', 'ok'))
    body = client.post('/api/native-dialog/save-file', json={}).get_json()
    assert body == {'ok': True, 'path': '/tmp/x.psd'}


# ── the Windows command, asserted structurally ────────────────────────────

def _windows_command(monkeypatch, which):
    """Capture the argv the Windows branch would run."""
    captured = {}

    def fake_run(cmd, what='dialog'):
        captured['cmd'] = cmd
        return None, 'cancelled'

    monkeypatch.setattr(rd.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(rd, '_run_dialog_command', fake_run)
    if which == 'directory':
        rd._native_choose_directory()
    else:
        rd._native_choose_save_file('Show.psd')
    return captured['cmd']


@pytest.mark.parametrize('which', ['directory', 'save'])
def test_the_windows_dialog_runs_single_threaded(monkeypatch, which):
    """WinForms throws outside an STA. Without this the dialog never opens and
    the export falls through to Downloads."""
    cmd = _windows_command(monkeypatch, which)
    assert '-STA' in cmd, cmd


@pytest.mark.parametrize('which', ['directory', 'save'])
def test_the_windows_dialog_is_given_a_topmost_owner(monkeypatch, which):
    """With no owner the dialog can open BEHIND the browser, which looks
    exactly like it never opened at all."""
    script = _windows_command(monkeypatch, which)[-1]
    assert 'TopMost=$true' in script, script
    assert 'ShowDialog($owner)' in script, script
    assert '$owner.Close()' in script, 'the hidden owner form is never disposed'


def test_the_windows_save_dialog_escapes_the_suggested_name(monkeypatch):
    """A project called Wall "A" would otherwise break out of the string, and
    a $ in a name would be interpolated by PowerShell."""
    captured = {}

    def fake_run(cmd, what='dialog'):
        captured['cmd'] = cmd
        return None, 'cancelled'

    monkeypatch.setattr(rd.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(rd, '_run_dialog_command', fake_run)
    rd._native_choose_save_file('Wall "A" $env:TEMP.psd')
    script = captured['cmd'][-1]
    assert '`"A`"' in script, script
    assert '`$env:TEMP' in script, script


def test_ps_quote_handles_every_special_character():
    assert rd._ps_quote('Wall "A" $env:TEMP `x') == 'Wall `"A`" `$env:TEMP ``x'
    assert rd._ps_quote('plain name') == 'plain name'


# ── the guard that keeps this host-only ───────────────────────────────────

def test_a_remote_client_still_cannot_open_a_dialog_on_the_host(client):
    """These routes open dialogs on, and write files to, the HOST. A LAN peer
    must not be able to do either - unchanged, asserted so it stays that way."""
    resp = client.post('/api/native-dialog/select-directory',
                       environ_overrides={'REMOTE_ADDR': '192.168.1.50'})
    assert resp.status_code == 403
    assert resp.get_json()['ok'] is False
