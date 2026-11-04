"""A beta build names itself and is offered its full release.

release.yml writes BUILD_TAG.txt ("1.5.3-beta.1") into beta builds only.
The app then reports that version everywhere it shows one: the header, the
window title, About, the update dialog, the launcher, a saved show. The
update check still reads only full releases (owner, 2026-10-19: "only the
final release"), and counts 1.5.3 as newer than 1.5.3-beta.1, so a beta
tester is told when the real one ships.
"""
import io
import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import updater  # noqa: E402
from updater import _version_key  # noqa: E402


@pytest.fixture(autouse=True)
def _keep_the_update_cache():
    """check_for_update caches its result for the whole server. A faked
    "1.5.3 is available" left in it put the update banner over the File
    menu of every browser module that ran after this one in the worker
    (full suite, 2026-10-19: the pull sheet editor's ten tests timed out
    on a click the banner intercepted)."""
    with updater._cache_lock:
        saved = dict(updater._cache)
    yield
    with updater._cache_lock:
        updater._cache.clear()
        updater._cache.update(saved)


def test_a_release_sorts_above_its_betas():
    order = ['1.5.1', '1.5.2-beta.1', '1.5.2-beta.2', '1.5.2-beta.10', '1.5.2', '1.5.3-beta.1', '1.6.0']
    assert sorted(order, key=_version_key) == order
    assert _version_key('v1.5.2') == _version_key('1.5.2')


@pytest.mark.parametrize(('version_txt', 'tag', 'expected'), [
    ('1.5.3', None, '1.5.3'),                  # a full release or a source run
    ('1.5.3', '1.5.3-beta.1', '1.5.3-beta.1'),  # a beta build
    ('1.5.3', '﻿v1.5.3-beta.2', '1.5.3-beta.2'),  # a BOM or a v stays harmless
    ('1.5.3', '1.5.3', '1.5.3'),                # not a prerelease: nothing to add
    ('1.5.3', '1.5.2-beta.4', '1.5.3'),         # a stale tag for another version is ignored
])
def test_the_running_version_names_a_beta(tmp_path, monkeypatch, version_txt, tag, expected):
    (tmp_path / 'VERSION.txt').write_text(f'v{version_txt} - October 19, 2026\n', encoding='utf-8')
    if tag is not None:
        (tmp_path / 'BUILD_TAG.txt').write_text(tag, encoding='utf-8')
    monkeypatch.setattr(updater.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(updater.sys, '_MEIPASS', str(tmp_path), raising=False)
    assert updater.get_current_version() == expected


def _release(tag):
    body = json.dumps({'tag_name': tag, 'html_url': 'https://example.invalid', 'body': '', 'assets': []})

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    return _Resp(body.encode('utf-8'))


@pytest.mark.parametrize(('current', 'latest', 'offered'), [
    ('1.5.3-beta.1', 'v1.5.3', True),    # the beta's own release ships
    ('1.5.3-beta.2', 'v1.5.2', False),   # an older release is not offered
    ('1.5.3', 'v1.5.3', False),          # already on it
    ('1.5.2', 'v1.5.3', True),
])
def test_a_beta_is_offered_its_full_release(current, latest, offered):
    with patch.object(updater, 'get_current_version', return_value=current), \
            patch.object(updater, 'urlopen', return_value=_release(latest)):
        result = updater.check_for_update(force=True)
    assert result['error'] is None, result
    assert result['current_version'] == current
    assert result['available'] is offered


def test_update_check_reads_only_full_releases():
    # /releases/latest never returns a prerelease, so a beta is never offered
    # another beta - only the final.
    assert updater.RELEASES_URL.endswith('/releases/latest')


pytest.importorskip("playwright.sync_api", reason="playwright not installed")


def test_the_page_names_a_beta_build(e2e_server, pw_browser):
    ctx = pw_browser.new_context()
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = ctx.new_page()
    pg.route('**/api/version', lambda route: route.fulfill(
        status=200, content_type='application/json', body=json.dumps({'version': '1.5.3-beta.1'})))
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => document.getElementById('app-version-label').textContent === 'v1.5.3-beta.1'")
        assert 'v1.5.3-beta.1' in pg.title()
        assert pg.evaluate("() => window.app.appVersion()") == '1.5.3-beta.1'
        stamped = pg.evaluate("() => JSON.parse(window.app.serializeProjectForFile()).app_version")
        assert stamped == '1.5.3-beta.1'
    finally:
        ctx.close()
