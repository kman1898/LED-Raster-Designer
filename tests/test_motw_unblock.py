"""Clearing Windows' Mark of the Web from the app's own bundled files.

Windows tags every file extracted from a downloaded .zip with a
Zone.Identifier alternate data stream. The .NET loader refuses to load a
tagged managed DLL, so pythonnet cannot resolve Python.Runtime.Loader.
Initialize, pywebview cannot start, and the app falls back to a browser
window - which is where the "export goes to Downloads" report began.

The documented workaround is "right-click the .zip, tick Unblock, extract
again", which nobody does. The app now clears the tag from its own files on
first run instead.

Windows-only behaviour, so the mechanics are asserted by driving the walk
against a fake filesystem rather than by needing a Windows host.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import launcher_window as lw  # noqa: E402


@pytest.fixture
def frozen_win(monkeypatch, tmp_path):
    """Pretend to be a frozen Windows build rooted at tmp_path."""
    monkeypatch.setattr(lw.sys, 'platform', 'win32')
    monkeypatch.setattr(lw.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(lw, 'APP_DIR', str(tmp_path))
    return tmp_path


def test_it_does_nothing_when_not_frozen(monkeypatch, tmp_path):
    """Running from source has no Mark of the Web and no bundle to walk."""
    monkeypatch.setattr(lw.sys, 'platform', 'win32')
    monkeypatch.setattr(lw.sys, 'frozen', False, raising=False)
    monkeypatch.setattr(lw, 'APP_DIR', str(tmp_path))
    removed = []
    monkeypatch.setattr(lw.os, 'remove', lambda p: removed.append(p))
    lw._clear_mark_of_the_web()
    assert removed == []


def test_it_does_nothing_off_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(lw.sys, 'platform', 'darwin')
    monkeypatch.setattr(lw.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(lw, 'APP_DIR', str(tmp_path))
    removed = []
    monkeypatch.setattr(lw.os, 'remove', lambda p: removed.append(p))
    lw._clear_mark_of_the_web()
    assert removed == []


def test_it_targets_loadable_code_and_leaves_data_alone(frozen_win, monkeypatch):
    """The DLLs are what the .NET loader refuses; walking the whole bundle
    would cost startup time for no benefit."""
    internal = frozen_win / '_internal' / 'pythonnet' / 'runtime'
    internal.mkdir(parents=True)
    (internal / 'Python.Runtime.dll').write_text('x')
    (frozen_win / 'LED Raster Designer.exe').write_text('x')
    (internal / 'clr_loader.pyd').write_text('x')
    (frozen_win / 'panel_catalog.json').write_text('{}')
    (frozen_win / 'notes.txt').write_text('x')

    removed = []
    monkeypatch.setattr(lw.os, 'remove', lambda p: removed.append(p))
    lw._clear_mark_of_the_web()

    targeted = {os.path.basename(p).split(':')[0] for p in removed}
    assert 'Python.Runtime.dll' in targeted, removed
    assert 'LED Raster Designer.exe' in targeted
    assert 'clr_loader.pyd' in targeted
    assert 'panel_catalog.json' not in targeted
    assert 'notes.txt' not in targeted
    assert all(p.endswith(':Zone.Identifier') for p in removed), removed


def test_it_runs_once_and_leaves_a_sentinel(frozen_win, monkeypatch):
    (frozen_win / 'a.dll').write_text('x')
    calls = []
    monkeypatch.setattr(lw.os, 'remove', lambda p: calls.append(p))

    lw._clear_mark_of_the_web()
    assert (frozen_win / lw._MOTW_SENTINEL).exists()
    first = len(calls)
    assert first > 0

    lw._clear_mark_of_the_web()   # second launch
    assert len(calls) == first, 'the walk repeated on a later launch'


def test_an_untagged_file_is_not_an_error(frozen_win, monkeypatch):
    """FileNotFoundError is the COMMON case - most files carry no tag."""
    (frozen_win / 'a.dll').write_text('x')

    def not_tagged(path):
        raise FileNotFoundError(path)
    monkeypatch.setattr(lw.os, 'remove', not_tagged)
    lw._clear_mark_of_the_web()   # must not raise
    assert (frozen_win / lw._MOTW_SENTINEL).exists()


def test_a_locked_file_does_not_stop_the_rest(frozen_win, monkeypatch):
    """A denied or locked file must not abort the walk - the remaining DLLs
    still need clearing, and a partial pass beats none."""
    for name in ('a.dll', 'b.dll', 'c.dll'):
        (frozen_win / name).write_text('x')
    seen = []

    def sometimes_denied(path):
        seen.append(path)
        if 'b.dll' in path:
            raise PermissionError(path)
    monkeypatch.setattr(lw.os, 'remove', sometimes_denied)
    lw._clear_mark_of_the_web()
    assert len(seen) == 3, seen


def test_a_read_only_install_dir_still_clears(frozen_win, monkeypatch):
    """The sentinel is an optimisation, not a precondition. If it cannot be
    written the work must still happen - just again next launch."""
    (frozen_win / 'a.dll').write_text('x')
    monkeypatch.setattr(lw.os, 'remove', lambda p: None)

    real_open = open

    def no_write(path, *a, **k):
        if str(path).endswith(lw._MOTW_SENTINEL):
            raise OSError('read-only')
        return real_open(path, *a, **k)
    monkeypatch.setattr('builtins.open', no_write)
    lw._clear_mark_of_the_web()   # must not raise
