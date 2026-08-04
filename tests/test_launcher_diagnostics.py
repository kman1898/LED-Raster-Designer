"""Launcher crash logging and window-fallback behaviour.

The frozen Windows build is windowed (console=False), so a startup failure has
nowhere to print. These cover the machinery that makes such a failure visible
and survivable instead of leaving an unquittable tray icon.
"""
import json
import os
import sys
import threading
import time

import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

launcher_window = pytest.importorskip('launcher_window')


@pytest.fixture
def caplog_events(monkeypatch):
    """Capture whatever the launcher writes to the app log."""
    events = []
    monkeypatch.setattr(
        launcher_window, '_launcher_log',
        lambda action, details, source='launcher': events.append(
            {'action': action, 'details': details}))
    return events


# ── crash logging ────────────────────────────────────────────────────────────

def test_excepthook_logs_uncaught_exception(caplog_events):
    launcher_window._install_crash_logger()
    try:
        raise ValueError('kaboom')
    except ValueError:
        sys.excepthook(*sys.exc_info())

    crashes = [e for e in caplog_events if e['action'] == 'launcher_crash']
    assert crashes, 'uncaught exception was not logged'
    details = crashes[0]['details']
    assert 'kaboom' in details['error']
    assert 'Traceback' in details['traceback']


def test_thread_excepthook_logs_and_names_thread(caplog_events):
    launcher_window._install_crash_logger()

    def boom():
        raise RuntimeError('thread-kaboom')

    t = threading.Thread(target=boom, name='probe')
    t.start()
    t.join()
    time.sleep(0.2)

    crashes = [e for e in caplog_events if e['action'] == 'launcher_crash']
    assert crashes, 'a thread death must not be silent'
    assert 'thread-kaboom' in crashes[0]['details']['error']
    assert crashes[0]['details']['thread'] == 'probe'


def test_format_exc_includes_traceback_for_raised_exception():
    def boom():
        raise RuntimeError('nope')
    try:
        boom()
    except RuntimeError as exc:
        text = launcher_window._format_exc(exc)
    assert 'Traceback' in text and 'nope' in text


# ── startup environment ──────────────────────────────────────────────────────

def test_startup_environment_logged(caplog_events):
    launcher_window._log_startup_environment()
    env = [e for e in caplog_events if e['action'] == 'launcher_environment']
    assert env, 'environment block missing'
    details = env[0]['details']
    for key in ('version', 'platform', 'frozen', 'python'):
        assert key in details


def test_startup_environment_reports_dotnet_on_windows(monkeypatch, caplog_events):
    monkeypatch.setattr(launcher_window.sys, 'platform', 'win32')
    monkeypatch.setattr(launcher_window, '_windows_dotnet_release', lambda: 394802)
    launcher_window._log_startup_environment()
    details = [e for e in caplog_events
               if e['action'] == 'launcher_environment'][0]['details']
    assert details['dotnet_framework_release'] == 394802
    # 4.6.2 is below the 4.7.2 needed to load pythonnet's netstandard2.0 DLL
    assert details['dotnet_framework_ok'] is False


@pytest.mark.parametrize('release,expected', [
    (None, 'does not appear to be installed'),
    (394802, 'older than 4.7.2'),          # 4.6.2
    (461808, 'blocking'),                  # 4.7.2 — .NET is fine, suspect MOTW/AV
    (528040, 'blocking'),                  # 4.8
])
def test_failure_hint_matches_dotnet_state(monkeypatch, release, expected):
    monkeypatch.setattr(launcher_window.sys, 'platform', 'win32')
    monkeypatch.setattr(launcher_window, '_windows_dotnet_release', lambda: release)
    assert expected in launcher_window._launcher_failure_hint()


def test_the_blocked_hint_leads_with_relaunching_not_right_clicking(monkeypatch):
    """The app now clears Mark of the Web from its own files on first run, so
    a second launch usually fixes this by itself. The old hint sent the user
    straight to "right-click the .zip and tick Unblock", which is a step
    nobody performs - it should be the fallback, not the headline."""
    monkeypatch.setattr(launcher_window.sys, 'platform', 'win32')
    monkeypatch.setattr(launcher_window, '_windows_dotnet_release', lambda: 528040)
    hint = launcher_window._launcher_failure_hint()
    assert 'once more' in hint, hint
    assert hint.index('once more') < hint.index('right-click'), (
        'the manual unblock should come after the self-healing advice')


# ── window fallback ──────────────────────────────────────────────────────────

def test_window_fallback_logs_opens_browser_and_degrades_api(monkeypatch, caplog_events):
    opened = []
    monkeypatch.setattr(launcher_window, 'open_url',
                        lambda url, settings: opened.append(url))
    monkeypatch.setattr(launcher_window, '_show_windows_error', lambda *a, **k: None)
    # Don't block the test in the keep-alive loop.
    monkeypatch.setattr(launcher_window.time, 'sleep',
                        lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(launcher_window.os, '_exit', lambda code: None)

    settings = {'interface': '127.0.0.1', 'port': 8050}
    api = launcher_window.LauncherAPI(settings)
    try:
        boom = RuntimeError('simulated webview failure')
        raise boom
    except RuntimeError as exc:
        launcher_window._launcher_window_fallback(settings, api, exc)

    failed = [e for e in caplog_events if e['action'] == 'launcher_window_failed']
    assert failed, 'window failure was not logged'
    details = failed[0]['details']
    assert 'simulated webview failure' in details['error']
    assert 'Traceback' in details['traceback']
    assert details['hint']

    assert opened == ['http://127.0.0.1:8050/'], 'browser fallback did not open'
    assert api._window_unavailable is True


def test_show_falls_back_to_browser_when_window_unavailable(monkeypatch):
    opened = []
    monkeypatch.setattr(launcher_window, 'open_url',
                        lambda url, settings: opened.append(url))
    api = launcher_window.LauncherAPI({'interface': '127.0.0.1', 'port': 8050})
    api.mark_window_unavailable()
    api.show()
    assert opened == ['http://127.0.0.1:8050/']


def test_quit_exits_even_without_a_window(monkeypatch):
    exits = []
    monkeypatch.setattr(launcher_window.os, '_exit', lambda code: exits.append(code))
    api = launcher_window.LauncherAPI({'interface': '127.0.0.1', 'port': 8050})
    api.mark_window_unavailable()
    api.quit()
    assert exits == [0], 'tray Quit must still exit with no window'


def test_launcher_log_falls_back_to_file_when_app_unimportable(monkeypatch, tmp_path):
    """A crash before app.py imports must still land on disk."""
    monkeypatch.setattr(launcher_window, 'APP_DIR', str(tmp_path))
    real_import = __builtins__['__import__'] if isinstance(__builtins__, dict) \
        else __builtins__.__import__

    def blocked(name, *args, **kwargs):
        if name == 'app':
            raise ImportError('simulated: app not importable yet')
        return real_import(name, *args, **kwargs)

    monkeypatch.setitem(sys.modules, 'app', None)
    monkeypatch.setattr('builtins.__import__', blocked)
    launcher_window._launcher_log('launcher_crash', {'error': 'early boom'})
    monkeypatch.setattr('builtins.__import__', real_import)

    fallback = tmp_path / 'launcher_crash.log'
    assert fallback.exists(), 'no on-disk record of an early crash'
    entry = json.loads(fallback.read_text().strip().splitlines()[-1])
    assert entry['action'] == 'launcher_crash'
    assert entry['details']['error'] == 'early boom'
