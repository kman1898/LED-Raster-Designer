"""Update in place on an installed Windows copy (owner, 2026-11-08).

Update downloads the release's setup, checks it against the release's
checksums.txt, and Install and restart runs it with /RELAUNCH and quits;
the setup reopens the app. A copy that is not installed by the setup
(macOS, the .zip, a source run) keeps the link to the release page.

No test here reaches the network, starts a setup or quits the test server:
the download is served by a fake opener, the setup launcher and the quit
are replaced (updater._spawn_installer, updater._schedule_quit).
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import updater  # noqa: E402

VERSION = '1.7.1'
NAME = f'led_raster_designer_v{VERSION}_windows_setup.exe'
URL = f'https://github.com/kman1898/LED-Raster-Designer/releases/download/v{VERSION}/{NAME}'
PAYLOAD = b'MZ' + b'\x00setup' * 5000
SHA = hashlib.sha256(PAYLOAD).hexdigest()
REAL_SPAWN = updater._spawn_installer   # before any test stands in for it


@pytest.fixture(autouse=True)
def _fresh_updater_state(tmp_path, monkeypatch):
    """Each test starts with no download, no cached check, downloads under
    tmp_path, and nothing that can run a setup or quit."""
    with updater._cache_lock:
        saved = dict(updater._cache)
        updater._cache.update(result=None, timestamp=0)
    with updater._dl_lock:
        saved_dl = dict(updater._dl)
        updater._dl.update(state='idle', percent=0, version=None, error=None, path=None, sha256=None)
    monkeypatch.setattr(updater.tempfile, 'tempdir', str(tmp_path))
    monkeypatch.setattr(updater, '_clean_old_downloads', lambda: None)
    monkeypatch.setattr(updater, '_page_waiting_path', lambda: str(tmp_path / 'update-page-waiting'))
    spawned, quits = [], []
    monkeypatch.setattr(updater, '_spawn_installer', lambda cmd: spawned.append(cmd))
    monkeypatch.setattr(updater, '_schedule_quit', lambda delay=1.0: quits.append(delay))
    yield {'spawned': spawned, 'quits': quits}
    with updater._cache_lock:
        updater._cache.clear()
        updater._cache.update(saved)
    with updater._dl_lock:
        updater._dl.clear()
        updater._dl.update(saved_dl)


def _offer(**over):
    result = {
        'available': True, 'current_version': '1.7.0', 'latest_version': VERSION,
        'download_url': f'https://github.com/kman1898/LED-Raster-Designer/releases/tag/v{VERSION}',
        'release_notes': '', 'checksums': {NAME: SHA}, 'checksums_url': None,
        'installer': {'name': NAME, 'url': URL, 'size': len(PAYLOAD)},
        'can_install': True, 'error': None,
    }
    result.update(over)
    return result


class _Resp(io.BytesIO):
    def __init__(self, data, length=True):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))} if length else {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Opener:
    def __init__(self, data=PAYLOAD, fail=None, gate=None):
        self.data, self.fail, self.gate, self.asked = data, fail, gate, []

    def open(self, req, timeout=None):
        self.asked.append(req.full_url)
        if self.gate is not None:
            self.gate.wait(5)
        if self.fail:
            raise self.fail
        return _Resp(self.data)


def _wait_state(*states, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        st = updater.download_status()
        if st['state'] in states:
            return st
        time.sleep(0.02)
    raise AssertionError(f'download never reached {states}: {updater.download_status()}')


def _installed(monkeypatch, yes=True):
    monkeypatch.setattr(updater, 'is_installed_copy', lambda *a, **k: yes)


# ── Which copies install in place ─────────────────────────────────────

INSTALL_DIR = r'C:\Users\crew\AppData\Local\Programs\LED Raster Designer'


@pytest.mark.parametrize(('registered', 'exe', 'platform', 'frozen', 'expected'), [
    (INSTALL_DIR + '\\', INSTALL_DIR + r'\LED Raster Designer.exe', 'win32', True, True),
    (INSTALL_DIR.lower(), INSTALL_DIR + r'\LED Raster Designer.exe', 'win32', True, True),
    ('"' + INSTALL_DIR + '"', INSTALL_DIR + r'\LED Raster Designer.exe', 'win32', True, True),
    # a .zip copy unpacked somewhere else, with an install on the machine too
    (INSTALL_DIR, r'C:\Users\crew\Desktop\LED Raster Designer App\LED Raster Designer.exe', 'win32', True, False),
    (None, INSTALL_DIR + r'\LED Raster Designer.exe', 'win32', True, False),     # never installed
    (INSTALL_DIR, INSTALL_DIR + r'\LED Raster Designer.exe', 'win32', False, False),  # source run
    (INSTALL_DIR, INSTALL_DIR + r'\LED Raster Designer.exe', 'darwin', True, False),  # macOS
])
def test_only_the_installed_windows_copy_installs(monkeypatch, registered, exe, platform, frozen, expected):
    monkeypatch.setattr(updater, '_registered_install_dir', lambda: registered)
    assert updater.is_installed_copy(platform=platform, frozen=frozen, executable=exe) is expected


def test_the_registry_key_is_the_setups_own():
    iss = open(os.path.join(ROOT, 'build', 'led_raster_designer.iss'), encoding='utf-8').read()
    assert 'AppId={' + updater.APP_ID + '\n' in iss.replace('\r\n', '\n')
    assert updater.UNINSTALL_KEY == (
        'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\' + updater.APP_ID + '_is1')


def test_this_test_run_is_not_an_installed_copy():
    assert updater.is_installed_copy() is False


# ── The setup asset ───────────────────────────────────────────────────

def _release(assets):
    return {'tag_name': 'v' + VERSION, 'assets': assets}


def test_the_setup_asset_is_found():
    asset = {'name': NAME, 'browser_download_url': URL, 'size': 123}
    assert updater.installer_asset(_release([asset]), VERSION) == {'name': NAME, 'url': URL, 'size': 123}
    beta = 'led_raster_designer_v1.7.0-beta.3_windows_setup.exe'
    beta_url = f'https://github.com/kman1898/LED-Raster-Designer/releases/download/v1.7.0-beta.3/{beta}'
    found = updater.installer_asset(_release([{'name': beta, 'browser_download_url': beta_url}]), '1.7.0-beta.3')
    assert found and found['name'] == beta


@pytest.mark.parametrize('url', [
    URL.replace('https://', 'http://'),
    URL.replace('github.com', 'github.com.example.net'),
    URL.replace('github.com', 'evil.example'),
    URL.replace('kman1898/LED-Raster-Designer', 'someone/LED-Raster-Designer'),
    URL + '?x=1',
    URL.replace(NAME, 'other.exe'),
    URL.replace('https://github.com', 'https://user@github.com'),
    URL.replace('github.com', 'github.com:8443'),
])
def test_a_setup_from_anywhere_else_is_refused(url):
    assert updater.installer_asset(_release([{'name': NAME, 'browser_download_url': url}]), VERSION) is None


def test_only_the_expected_file_name_counts():
    zip_name = f'led_raster_designer_v{VERSION}_windows.zip'
    assets = [{'name': zip_name, 'browser_download_url': URL.replace(NAME, zip_name)}]
    assert updater.installer_asset(_release(assets), VERSION) is None
    assert updater.installer_asset(_release([]), '../../evil') is None


def test_checksums_name_the_file_not_the_build_folder():
    text = (f'{SHA}  windows-build/{NAME}\n'
            'abc123  macos-build/led_raster_designer_v1.7.1_macos.dmg\n').encode('utf-8')
    with patch.object(updater, 'urlopen', return_value=_Resp(text)):
        sums = updater._fetch_checksums('https://example.invalid/checksums.txt', None)
    assert sums[NAME] == SHA
    assert 'led_raster_designer_v1.7.1_macos.dmg' in sums


def test_the_check_says_when_this_copy_can_install(monkeypatch):
    release = {'tag_name': 'v' + VERSION, 'html_url': 'https://example.invalid', 'body': '',
               'assets': [{'name': NAME, 'browser_download_url': URL, 'size': 9}]}

    def fake(req, timeout=None, context=None):
        return _Resp(json.dumps(release).encode('utf-8'))
    for installed in (True, False):
        _installed(monkeypatch, installed)
        with patch.object(updater, 'get_current_version', return_value='1.7.0'), \
                patch.object(updater, 'urlopen', side_effect=fake):
            result = updater.check_for_update(force=True)
        assert result['available'] is True
        assert result['installer']['name'] == NAME
        assert result['can_install'] is installed
        assert result['download_url'] == 'https://example.invalid'   # the link stays for the rest


# ── Downloading ───────────────────────────────────────────────────────

def _download(monkeypatch, opener, offer=None):
    _installed(monkeypatch)
    monkeypatch.setattr(updater, 'check_for_update', lambda force=False: offer or _offer())
    monkeypatch.setattr(updater, '_download_opener', lambda ctx: opener)
    first = updater.start_download()
    assert first['state'] == 'downloading'
    return _wait_state('ready', 'error')


def test_a_download_that_matches_its_checksum_is_ready(monkeypatch, tmp_path):
    opener = _Opener()
    st = _download(monkeypatch, opener)
    assert st == {'state': 'ready', 'percent': 100, 'version': VERSION, 'error': None}
    assert opener.asked == [URL]
    path = updater._dl['path']
    assert os.path.dirname(os.path.dirname(path)) == str(tmp_path)   # under %TEMP%, never the desktop
    assert os.path.basename(path) == NAME
    with open(path, 'rb') as fh:
        assert fh.read() == PAYLOAD


def test_a_mismatch_is_refused_and_deleted(monkeypatch, tmp_path):
    st = _download(monkeypatch, _Opener(data=PAYLOAD + b'tampered'))
    assert st['state'] == 'error'
    assert st['error'] == updater.MSG_BAD_CHECKSUM
    assert 'did not match the release' in st['error'] and 'try again' in st['error']
    assert not list(tmp_path.rglob('*.exe'))
    assert updater._dl['path'] is None


def test_a_missing_checksum_is_refused_and_deleted(monkeypatch, tmp_path):
    with patch.object(updater, '_fetch_checksums', return_value={'other.exe': 'abc'}) as again:
        st = _download(monkeypatch, _Opener(), offer=_offer(checksums=None, checksums_url='https://x.invalid/c'))
    assert again.called   # asked the release once more before refusing
    assert st['state'] == 'error'
    assert st['error'] == updater.MSG_NO_CHECKSUM
    assert not list(tmp_path.rglob('*.exe'))


def test_a_network_failure_says_so_plainly(monkeypatch, tmp_path):
    st = _download(monkeypatch, _Opener(fail=OSError('connection reset')))
    assert st['state'] == 'error'
    assert st['error'] == updater.MSG_NETWORK
    assert not list(tmp_path.rglob('*.exe'))


def test_a_copy_that_cannot_install_downloads_nothing(monkeypatch):
    _installed(monkeypatch, False)
    monkeypatch.setattr(updater, 'check_for_update', lambda force=False: _offer())
    st = updater.start_download()
    assert st['state'] == 'error' and st['error'] == updater.MSG_CANNOT_INSTALL
    assert updater.download_status()['state'] == 'idle'


def test_no_update_downloads_nothing(monkeypatch):
    _installed(monkeypatch)
    monkeypatch.setattr(updater, 'check_for_update', lambda force=False: _offer(available=False))
    assert updater.start_download()['error'] == updater.MSG_NO_UPDATE


def test_one_download_at_a_time(monkeypatch):
    gate = threading.Event()
    opener = _Opener(gate=gate)
    _installed(monkeypatch)
    monkeypatch.setattr(updater, 'check_for_update', lambda force=False: _offer())
    monkeypatch.setattr(updater, '_download_opener', lambda ctx: opener)
    assert updater.start_download()['state'] == 'downloading'
    assert updater.start_download()['state'] == 'downloading'
    assert updater.start_download()['state'] == 'downloading'
    gate.set()
    _wait_state('ready')
    assert len(opener.asked) == 1
    # Ready stays ready: Update again does not fetch it twice.
    assert updater.start_download()['state'] == 'ready'
    assert len(opener.asked) == 1


def test_redirects_only_to_github():
    handler = [h for h in updater._download_opener(None).handlers
               if type(h).__name__ == '_GitHubRedirectsOnly'][0]
    from urllib.request import Request
    from urllib.error import HTTPError
    req = Request(URL)
    for ok in ('https://objects.githubusercontent.com/x', 'https://release-assets.githubusercontent.com/x'):
        assert handler.redirect_request(req, None, 302, 'Found', {}, ok) is not None
    for bad in ('http://objects.githubusercontent.com/x', 'https://evil.example/x'):
        with pytest.raises(HTTPError):
            handler.redirect_request(req, None, 302, 'Found', {}, bad)


# ── Installing ────────────────────────────────────────────────────────

def _ready(monkeypatch, tmp_path, data=PAYLOAD):
    _installed(monkeypatch)
    folder = tmp_path / 'lrd-update-test'
    folder.mkdir()
    path = folder / NAME
    path.write_bytes(data)
    updater._dl.update(state='ready', percent=100, version=VERSION, error=None, path=str(path), sha256=SHA)
    return path


def test_install_runs_the_checked_setup_with_relaunch_and_quits(monkeypatch, tmp_path, _fresh_updater_state):
    path = _ready(monkeypatch, tmp_path)
    assert updater.install_update() == {'ok': True, 'version': VERSION}
    [cmd] = _fresh_updater_state['spawned']
    assert cmd[0] == str(path)
    assert cmd[1:6] == ['/SILENT', '/SP-', '/SUPPRESSMSGBOXES', '/NORESTART', '/RELAUNCH']
    assert cmd[6].startswith('/LOG=')
    assert _fresh_updater_state['quits'] == [1.0]
    assert updater.download_status()['state'] == 'installing'


def test_a_setup_changed_after_the_check_is_never_run(monkeypatch, tmp_path, _fresh_updater_state):
    path = _ready(monkeypatch, tmp_path)
    path.write_bytes(PAYLOAD + b'swapped')
    result = updater.install_update()
    assert result == {'ok': False, 'error': updater.MSG_BAD_CHECKSUM}
    assert not path.exists()
    assert _fresh_updater_state['spawned'] == [] and _fresh_updater_state['quits'] == []


def test_install_before_the_download_is_ready_does_nothing(_fresh_updater_state):
    assert updater.install_update() == {'ok': False, 'error': updater.MSG_NOT_READY}
    assert _fresh_updater_state['spawned'] == []


def test_the_setup_starts_without_the_bundles_environment(monkeypatch):
    monkeypatch.setenv('_PYI_APPLICATION_HOME_DIR', r'C:\app\_internal')
    monkeypatch.setenv('_MEIPASS2', r'C:\app\_internal')
    monkeypatch.setenv('_LRD_LOG_DIR', r'C:\logs')
    monkeypatch.setenv('LRD_KEEP_ME', '1')
    env = updater._installer_env()
    assert '_PYI_APPLICATION_HOME_DIR' not in env and '_MEIPASS2' not in env and '_LRD_LOG_DIR' not in env
    assert env['LRD_KEEP_ME'] == '1'
    assert env['PYINSTALLER_RESET_ENVIRONMENT'] == '1'


def test_the_real_launcher_is_detached(monkeypatch):
    """The real _spawn_installer (the fixture stands in for it elsewhere):
    detached and in its own group, so it outlives the app. Popen is faked."""
    calls = []

    class _Popen:
        def __init__(self, cmd, **kw):
            calls.append((cmd, kw))
    monkeypatch.setattr(subprocess, 'Popen', _Popen)
    REAL_SPAWN([os.path.join('C:\\tmp', NAME), '/SILENT'])
    [(cmd, kw)] = calls
    assert cmd == [os.path.join('C:\\tmp', NAME), '/SILENT']
    flags = kw['creationflags']
    assert flags & 0x00000008 and flags & 0x00000200    # DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP
    assert kw['stdin'] == subprocess.DEVNULL and kw['close_fds'] is True
    assert kw['env']['PYINSTALLER_RESET_ENVIRONMENT'] == '1'


# ── One browser tab across the restart ────────────────────────────────

def test_install_leaves_a_note_for_the_next_launch(monkeypatch, tmp_path):
    _ready(monkeypatch, tmp_path)
    assert updater.install_update()['ok'] is True
    assert (tmp_path / 'update-page-waiting').is_file()


@pytest.mark.parametrize(('setting', 'note_age', 'opens'), [
    (True, None, True),      # an ordinary launch with Open Browser on Launch
    (False, None, False),    # the setting off
    (True, 20, False),       # the relaunch: the old page is waiting and reloads
    (True, 590, False),      # a slow install still counts
    (True, 601, True),       # a stale note (setup failed, opened by hand later)
    (True, -5, True),        # a clock that went backwards: no promise of a page
    (False, 20, False),
])
def test_the_relaunch_opens_no_second_tab(tmp_path, setting, note_age, opens):
    now = 1_000_000.0
    if note_age is not None:
        updater.mark_page_waiting(now=now - note_age)
    with patch.object(updater.time, 'time', return_value=now):
        assert updater.open_browser_on_launch({'open_browser_on_launch': setting}) is opens
    # Read once: the launch after that opens the browser as usual.
    assert not (tmp_path / 'update-page-waiting').exists()
    assert updater.open_browser_on_launch({'open_browser_on_launch': setting}) is setting


def test_a_garbled_note_is_dropped(tmp_path):
    (tmp_path / 'update-page-waiting').write_text('not a time', encoding='utf-8')
    assert updater.open_browser_on_launch({'open_browser_on_launch': True}) is True
    assert not (tmp_path / 'update-page-waiting').exists()


def test_both_launchers_ask_before_opening_the_browser():
    for name in ('launcher_window.py', 'launcher_pc.py'):
        src = open(os.path.join(ROOT, 'src', name), encoding='utf-8').read()
        assert 'if updater.open_browser_on_launch(settings):' in src, name
        assert "if settings.get('open_browser_on_launch', False):\n        open_url" not in src, name


# ── The routes ────────────────────────────────────────────────────────

def test_the_check_route_offers_install_only_to_the_host(client, monkeypatch):
    import routes_version
    monkeypatch.setattr(routes_version, 'check_for_update', lambda force=False: _offer())
    assert client.get('/api/update/check').get_json()['can_install'] is True
    remote = client.get('/api/update/check', environ_base={'REMOTE_ADDR': '10.250.1.9'}).get_json()
    assert remote['can_install'] is False
    assert remote['download_url']   # the link stays


def test_the_check_route_never_offers_install_when_the_copy_cannot(client, monkeypatch):
    import routes_version
    monkeypatch.setattr(routes_version, 'check_for_update', lambda force=False: _offer(can_install=False))
    assert client.get('/api/update/check').get_json()['can_install'] is False


def test_download_and_status_routes(client, monkeypatch):
    opener = _Opener()
    _installed(monkeypatch)
    monkeypatch.setattr(updater, 'check_for_update', lambda force=False: _offer())
    monkeypatch.setattr(updater, '_download_opener', lambda ctx: opener)
    first = client.post('/api/update/download').get_json()
    assert first['state'] in ('downloading', 'verifying', 'ready')
    _wait_state('ready')
    st = client.get('/api/update/status').get_json()
    assert st == {'state': 'ready', 'percent': 100, 'version': VERSION, 'error': None}
    assert client.post('/api/update/download').get_json()['state'] == 'ready'
    assert len(opener.asked) == 1


def test_another_device_cannot_download_or_install(client, monkeypatch, tmp_path, _fresh_updater_state):
    _ready(monkeypatch, tmp_path)
    away = {'REMOTE_ADDR': '10.250.1.9'}
    assert client.post('/api/update/download', environ_base=away).status_code == 403
    assert client.post('/api/update/install', json={'discard': True}, environ_base=away).status_code == 403
    assert _fresh_updater_state['spawned'] == []


def test_install_route_asks_about_unsaved_work_first(client, monkeypatch, tmp_path, _fresh_updater_state):
    import routes_project
    _ready(monkeypatch, tmp_path)
    routes_project.set_project_unsaved(True)
    try:
        resp = client.post('/api/update/install', json={})
        assert resp.status_code == 409
        assert resp.get_json()['unsaved'] is True
        assert _fresh_updater_state['spawned'] == [] and _fresh_updater_state['quits'] == []
        # The user answered (Don't Save, or Install anyway): it goes ahead.
        resp = client.post('/api/update/install', json={'discard': True})
        assert resp.status_code == 200 and resp.get_json()['ok'] is True
    finally:
        routes_project.set_project_unsaved(False)
    assert len(_fresh_updater_state['spawned']) == 1
    assert _fresh_updater_state['quits'] == [1.0]


def test_install_route_with_nothing_unsaved_goes_ahead(client, monkeypatch, tmp_path, _fresh_updater_state):
    import routes_project
    routes_project.set_project_unsaved(False)
    _ready(monkeypatch, tmp_path)
    resp = client.post('/api/update/install', json={})
    assert resp.status_code == 200 and resp.get_json() == {'ok': True, 'version': VERSION}
    assert '/RELAUNCH' in _fresh_updater_state['spawned'][0]


def test_install_route_refuses_before_the_download(client, _fresh_updater_state):
    resp = client.post('/api/update/install', json={'discard': True})
    assert resp.status_code == 400
    assert resp.get_json()['error'] == updater.MSG_NOT_READY
    assert _fresh_updater_state['spawned'] == []


# ── Plain words ───────────────────────────────────────────────────────

def test_messages_are_plain():
    msgs = [updater.MSG_NETWORK, updater.MSG_NO_CHECKSUM, updater.MSG_BAD_CHECKSUM,
            updater.MSG_CANNOT_INSTALL, updater.MSG_NO_UPDATE, updater.MSG_NOT_READY]
    js = open(os.path.join(ROOT, 'src', 'static', 'js', 'updater.js'), encoding='utf-8').read()
    for text in msgs + ["'Install and restart'", "'Update'", "'Downloading '"]:
        for bad in ('\u2014', '\u2013', ' - '):
            assert bad not in text, text
    for word in ("'Update'", "'Install and restart'", "'Downloading '"):
        assert word in js


# ── The CI script drives the same code ────────────────────────────────

def test_the_smoke_script_fetches_through_the_updater(tmp_path, monkeypatch):
    """scripts/update_smoke.py fetch, as release.yml runs it: served over
    127.0.0.1, downloaded by the updater's worker, checksum checked, and
    on Windows no Zone.Identifier on the copy."""
    sys.path.insert(0, os.path.join(ROOT, 'scripts'))
    try:
        import update_smoke
    finally:
        sys.path.pop(0)
    served = tmp_path / 'served'
    served.mkdir()
    setup = served / NAME
    setup.write_bytes(PAYLOAD)
    out = tmp_path / 'fetched.txt'
    assert update_smoke.main(['fetch', str(setup), VERSION, str(out)]) == 0
    fetched = out.read_text(encoding='utf-8')
    assert fetched != str(setup) and os.path.isfile(fetched)
    assert updater.verify_download(fetched, SHA)
    if sys.platform == 'win32':
        assert update_smoke.has_zone_identifier(fetched) is False
