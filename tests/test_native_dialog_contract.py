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


# ── a NON-ZERO exit can still be a cancel ─────────────────────────────────
#
# Reported on macOS after the status split shipped: Cancel on the export
# dialog still dropped the files into Downloads. The app log said why -
#
#   native_dialog_command_failed  {"cmd": "osascript", "returncode": 1,
#      "stderr": "15:85: execution error: User canceled. (-128)"}
#   native_dialog_save_file_no_path {"status": "unavailable"}
#   save_blob_browser_download
#
# - osascript reports a dismissed dialog as a FAILED run, so "exit 0 with no
# path" never fired and every Cancel was classed as a broken dialog. Both
# dialogs were affected; picking a folder always worked.
#
# The signature per helper, which is what these tests pin:
#   osascript   exit 1, AppleScript error -128 on stderr
#   zenity      exit 1, nothing said on either stream
#   powershell  exit 0, nothing on stdout (the scripts only Write-Output on
#               DialogResult::OK) - the older branch, still covered above

def _finished(returncode=0, stdout='', stderr=''):
    """A stand-in for what subprocess.run hands back. Mocked rather than
    driven for real: these cases need a dialog somebody actually clicks."""
    return subprocess.CompletedProcess(
        args=['helper'], returncode=returncode, stdout=stdout, stderr=stderr)


def _run_with(monkeypatch, cmd, **outcome):
    monkeypatch.setattr(rd.subprocess, 'run',
                        lambda *a, **k: _finished(**outcome))
    return rd._run_dialog_command(cmd, 'probe')


def test_an_osascript_cancel_is_a_cancel_not_a_broken_dialog(monkeypatch):
    """The reported bug, verbatim from the log."""
    path, status = _run_with(
        monkeypatch, ['osascript', '-e', 'choose folder'],
        returncode=1, stderr='15:63: execution error: User canceled. (-128)')
    assert path is None
    assert status == 'cancelled', (
        'a cancelled export must save nothing - classing this as unavailable '
        'is what sent the files to Downloads')


@pytest.mark.parametrize('stderr', [
    '6:29: execution error: Usuario ha cancelado. (-128)',
    '6:29: execution error: L’utilisateur a annulé. (-128)',
    '6:29: execution error: ユーザーが取り消しました。 (-128)',
])
def test_a_cancel_on_a_non_english_system_is_still_a_cancel(monkeypatch, stderr):
    """THE reason this matches the error number and not the sentence.

    osascript localises the message beside the code but never the code, so
    matching "User canceled" would have left every non-English machine with
    the original bug and no sign of it in an English-language log.
    """
    path, status = _run_with(monkeypatch, ['osascript', '-e', 'x'],
                             returncode=1, stderr=stderr)
    assert status == 'cancelled', stderr


@pytest.mark.parametrize('stderr', [
    # A script that will not compile - same exit code, different number.
    "12:26: syntax error: A parameter name can't go after this property. (-2740)",
    # TCC refusing the automation prompt. The dialog genuinely never opened,
    # so the export must still fall back rather than be thrown away.
    '0:0: execution error: Not authorized to send Apple events. (-1743)',
    'osascript: no such file or directory',
])
def test_a_real_osascript_failure_is_still_unavailable(monkeypatch, stderr):
    """The opposite bug, and the worse one: treat every non-zero exit as a
    cancel and a genuinely broken dialog silently loses the export."""
    path, status = _run_with(monkeypatch, ['osascript', '-e', 'x'],
                             returncode=1, stderr=stderr)
    assert status == 'unavailable', stderr


def test_the_cancel_code_is_matched_whole(monkeypatch):
    """-1288 is not -128. Loose matching would turn an unrelated failure into
    a cancel and lose the export."""
    path, status = _run_with(monkeypatch, ['osascript', '-e', 'x'],
                             returncode=1,
                             stderr='1:2: execution error: something (-1288)')
    assert status == 'unavailable'


def test_a_zenity_cancel_is_a_cancel(monkeypatch):
    """zenity documents exit 1 for "cancel, or no file selected", and says
    nothing on either stream when that is what happened."""
    path, status = _run_with(monkeypatch,
                             ['zenity', '--file-selection', '--directory'],
                             returncode=1)
    assert path is None
    assert status == 'cancelled'


def test_a_zenity_that_cannot_open_a_display_is_unavailable(monkeypatch):
    """zenity exits 1 for this too - so exit code alone cannot decide it. A
    cancel is silent; a failure explains itself, and that is the difference."""
    path, status = _run_with(monkeypatch, ['zenity', '--file-selection'],
                             returncode=1,
                             stderr='Unable to init server: Could not connect: '
                                    'Connection refused')
    assert status == 'unavailable'


def test_a_zenity_crash_is_unavailable(monkeypatch):
    path, status = _run_with(monkeypatch, ['zenity', '--file-selection'],
                             returncode=139)
    assert status == 'unavailable'


def test_a_windows_cancel_arrives_as_a_clean_exit_with_no_path(monkeypatch):
    """The PowerShell scripts only Write-Output on DialogResult::OK, so a
    Cancel is exit 0 and an empty stdout. Asserted so the platform that
    already worked keeps working."""
    path, status = _run_with(monkeypatch, ['powershell', '-NoProfile', '-STA',
                                           '-Command', '...'],
                             returncode=0, stdout='   \n')
    assert path is None
    assert status == 'cancelled'


def test_a_powershell_that_threw_is_unavailable(monkeypatch):
    """No catch in the script, so an exception escapes and PowerShell exits
    non-zero. That is a dialog that never opened - fall back, do not discard."""
    path, status = _run_with(monkeypatch, ['powershell.exe', '-Command', '...'],
                             returncode=1,
                             stderr='New-Object : Cannot find type '
                                    '[System.Windows.Forms.SaveFileDialog]')
    assert status == 'unavailable'


# ── the log has to tell the two apart at a glance ─────────────────────────

def _events(monkeypatch):
    seen = []
    monkeypatch.setattr(rd, 'log_event',
                        lambda name, payload=None: seen.append(name))
    return seen


def test_a_cancel_is_logged_as_a_cancel(monkeypatch):
    """It was logged as native_dialog_command_failed, which is what made this
    read as a broken dialog for as long as it did."""
    seen = _events(monkeypatch)
    _run_with(monkeypatch, ['osascript', '-e', 'x'], returncode=1,
              stderr='15:85: execution error: User canceled. (-128)')
    assert 'native_dialog_cancelled' in seen
    assert 'native_dialog_command_failed' not in seen


def test_a_failure_is_still_logged_as_a_failure(monkeypatch):
    seen = _events(monkeypatch)
    _run_with(monkeypatch, ['osascript', '-e', 'x'], returncode=1,
              stderr='0:0: execution error: Not authorized. (-1743)')
    assert 'native_dialog_command_failed' in seen
    assert 'native_dialog_cancelled' not in seen


# ── and it reaches the client, which is the only thing that matters ───────

@pytest.mark.parametrize('route', [
    '/api/native-dialog/save-file',
    '/api/native-dialog/select-directory',
])
def test_an_osascript_cancel_reaches_the_browser_as_a_cancel(
        client, monkeypatch, route):
    """End to end from the subprocess result to the JSON the export code
    branches on: {cancelled:true} makes it show "Export cancelled - nothing
    was saved", {unavailable:true} makes it download to Downloads instead."""
    monkeypatch.setattr(rd.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(rd.subprocess, 'run', lambda *a, **k: _finished(
        returncode=1,
        stderr='15:85: execution error: User canceled. (-128)'))
    body = client.post(route, json={'suggested_name': 'Show.png'}).get_json()
    assert body['ok'] is False
    assert body['cancelled'] is True
    assert body['unavailable'] is False


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

def test_a_remote_client_still_cannot_open_a_dialog_on_the_host(client, monkeypatch):
    """These routes open dialogs on, and write files to, the HOST. A LAN peer
    must not be able to do either - unchanged, asserted so it stays that way."""
    # Pin the trusted set: without this the test depends on the developer's
    # own DHCP lease, and 192.168.1.50 is a perfectly plausible one.
    monkeypatch.setattr(rd, '_own_addresses', lambda: {'127.0.0.1', '::1'})
    resp = client.post('/api/native-dialog/select-directory',
                       environ_overrides={'REMOTE_ADDR': '192.168.1.50'})
    assert resp.status_code == 403
    assert resp.get_json()['ok'] is False


# ── the host reached at its OWN LAN address is still the host ─────────────
#
# Reported: export kept dropping files into Downloads on Windows even after
# the dialog fix. The log showed why, and it was not the dialog at all:
#
#   server_start   {"host": "192.168.2.5", "port": 8050}
#   url            "http://192.168.2.5:8050/"
#   message        "remote client: skip host dialog"
#
# The launcher had bound the server to a network interface so the drawing
# could be opened from another machine. The HOST's own browser then reached
# the app at that LAN address too, so request.remote_addr was the machine's
# own IP rather than 127.0.0.1 - and a loopback-only test called the host a
# remote client and deliberately skipped the folder chooser.
#
# (A second, independent blocker in the same situation: Chrome only exposes
# showDirectoryPicker in a secure context, so http://192.168.2.5 gets no File
# System Access API either. Both routes to a chooser were shut at once, which
# is why the fallback was the only thing left.)

def test_the_machines_own_lan_address_counts_as_the_host(monkeypatch):
    monkeypatch.setattr(rd, '_own_addresses',
                        lambda: {'127.0.0.1', '::1', '192.168.2.5'})
    assert rd._is_same_machine('192.168.2.5') is True
    assert rd._is_same_machine('127.0.0.1') is True


def test_a_different_machine_on_the_same_lan_is_not_the_host(monkeypatch):
    """The security property that must NOT be weakened: a LAN peer still
    cannot open a dialog on, or write a file to, this machine."""
    monkeypatch.setattr(rd, '_own_addresses',
                        lambda: {'127.0.0.1', '::1', '192.168.2.5'})
    assert rd._is_same_machine('192.168.2.9') is False
    assert rd._is_same_machine('10.0.0.4') is False
    assert rd._is_same_machine('') is False
    assert rd._is_same_machine(None) is False


def test_own_addresses_always_contains_loopback():
    addrs = rd._own_addresses()
    assert '127.0.0.1' in addrs
    assert '::1' in addrs


def test_the_bound_interface_is_what_makes_the_host_the_host(monkeypatch):
    """The POINT of the change, tested end to end rather than around.

    An audit found the first version derived the address set from
    socket.gethostname(), which MISSES a secondary NIC - the exact case the
    feature exists for - so the host stayed misclassified and Export still
    went to Downloads. And the tests monkeypatched _own_addresses, so they
    proved nothing about the real one.
    """
    import app as app_module
    monkeypatch.setattr(app_module, 'BOUND_HOST', '10.77.0.5', raising=False)
    assert rd._bound_host() == '10.77.0.5'
    assert rd._is_same_machine('10.77.0.5') is True
    assert rd._is_same_machine('10.77.0.9') is False


def test_binding_all_interfaces_names_no_particular_address(monkeypatch):
    """0.0.0.0 means "everything" and therefore identifies nothing. Loopback
    still qualifies; a LAN peer must not."""
    import app as app_module
    monkeypatch.setattr(app_module, 'BOUND_HOST', '0.0.0.0', raising=False)
    assert rd._bound_host() is None
    assert rd._is_same_machine('127.0.0.1') is True


def test_it_fails_closed_when_the_bound_address_is_unknown(monkeypatch):
    """Losing the folder chooser is annoying. Trusting an address we cannot
    vouch for is not - so the unknown case must not widen the set."""
    import app as app_module
    monkeypatch.setattr(app_module, 'BOUND_HOST', None, raising=False)
    monkeypatch.setattr(rd, '_default_route_address', lambda: None)
    assert rd._own_addresses() == set(rd._LOOPBACK)


def test_no_address_comes_from_name_resolution(monkeypatch):
    """Hard rule. A hostile or misconfigured DNS/mDNS responder must not be
    able to put a peer's IP into the trusted set - that set gates
    /api/native-dialog/write-file, which writes to any absolute path."""
    import app as app_module
    monkeypatch.setattr(app_module, 'BOUND_HOST', None, raising=False)
    monkeypatch.setattr(rd, '_default_route_address', lambda: None)

    def poisoned(*a, **k):
        raise AssertionError('_own_addresses must not consult DNS')
    monkeypatch.setattr(rd.socket, 'gethostbyname', poisoned)
    monkeypatch.setattr(rd.socket, 'getaddrinfo', poisoned)
    assert rd._own_addresses() == set(rd._LOOPBACK)


def test_ipv4_mapped_ipv6_is_the_same_machine(monkeypatch):
    """A client reaching an IPv4 service over a dual-stack socket presents
    ::ffff:a.b.c.d."""
    import app as app_module
    monkeypatch.setattr(app_module, 'BOUND_HOST', '10.77.0.5', raising=False)
    assert rd._is_same_machine('::ffff:10.77.0.5') is True
    assert rd._is_same_machine('::ffff:10.77.0.9') is False


def test_the_availability_probe_answers_for_the_host(client):
    """The browser cannot work this out for itself - it only sees the address
    it was opened at. This endpoint is how it asks."""
    resp = client.get('/api/native-dialog/available')
    assert resp.status_code == 200
    assert resp.get_json()['host'] is True


def test_the_availability_probe_refuses_a_remote_client(client, monkeypatch):
    monkeypatch.setattr(rd, '_own_addresses', lambda: {'127.0.0.1', '::1'})
    resp = client.get('/api/native-dialog/available',
                      environ_overrides={'REMOTE_ADDR': '192.168.99.99'})
    assert resp.status_code == 403, (
        'a LAN peer must not be told it can open dialogs on this machine')


def test_a_lan_peer_still_cannot_write_files_to_the_host(client, monkeypatch):
    """The whole point of the loopback guard, re-asserted after widening it."""
    monkeypatch.setattr(rd, '_own_addresses', lambda: {'127.0.0.1', '::1'})
    resp = client.post('/api/native-dialog/write-file',
                       environ_overrides={'REMOTE_ADDR': '192.168.99.99'},
                       data={'path': '/tmp/should-never-happen.txt'})
    assert resp.status_code == 403
