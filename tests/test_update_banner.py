"""The update banner, in the browser (owner, 2026-11-08).

An installed Windows copy: Help > Check for Updates shows the banner with
an Update button; Update shows the download's progress, then Install and
restart, which asks the server to run the setup. Any other copy keeps the
Download link to the release page.

Every /api/update/* answer is the page's own route here, so nothing is
downloaded, no setup runs and the test server never quits
(tests/test_update_in_place.py holds the server side).

Run locally (each session takes its own free port):
    python -m pytest tests/test_update_banner.py -v --browser chromium
"""
import json

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

# The startup check (3 s after load) would show the banner by itself; 9.9.9
# dismissed keeps it quiet, so only Help > Check for Updates shows it here
# (a user's check ignores a dismiss).
NO_GUIDE = ("try{localStorage.setItem('lrd_quickstart_first_run_done','1');"
            "localStorage.setItem('lrd-update-dismissed-9.9.9','1');}catch(e){}")

CHECK = {
    'available': True, 'current_version': '1.7.0', 'latest_version': '9.9.9',
    'download_url': 'https://github.com/kman1898/LED-Raster-Designer/releases/tag/v9.9.9',
    'release_notes': '', 'checksums': None, 'installer': None, 'can_install': True, 'error': None,
}
BAD_SUM = ('The update was not installed because the download did not match the release, '
           'so it was deleted. Click Update to try again.')


def _json(route, body, status=200):
    route.fulfill(status=status, content_type='application/json', body=json.dumps(body))


def _open(pw_browser, url, check, statuses):
    """The page with the update routes answered here. `statuses` is the
    run of /api/update/status answers once Update was clicked."""
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(NO_GUIDE)
    pg = context.new_page()
    seen = {'download': 0, 'status': 0, 'install': []}
    problems = []
    pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))
    pg.on('dialog', lambda d: (problems.append(f'native {d.type}: {d.message}'), d.dismiss()))

    def on_download(route):
        seen['download'] += 1
        _json(route, {'state': 'downloading', 'percent': 0, 'version': '9.9.9', 'error': None})

    def on_status(route):
        if not seen['download']:
            _json(route, {'state': 'idle', 'percent': 0, 'version': None, 'error': None})
            return
        i = min(seen['status'], len(statuses) - 1)
        seen['status'] += 1
        _json(route, statuses[i])

    def on_install(route):
        seen['install'].append(json.loads(route.request.post_data or '{}'))
        _json(route, {'ok': True, 'version': '9.9.9'})

    pg.route('**/api/update/check**', lambda r: _json(r, check))
    pg.route('**/api/update/download', on_download)
    pg.route('**/api/update/status', on_status)
    pg.route('**/api/update/install', on_install)
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.wait_for_timeout(300)
    return context, pg, seen, problems


def _check_for_updates(pg):
    pg.locator('#menu-bar .menu-item[data-menu="help"]').click()
    pg.locator('#menu-help .menu-option[data-action="check-updates"]').click()
    pg.wait_for_function("() => document.getElementById('update-banner').style.display !== 'none'", timeout=5000)


def _text(pg):
    return pg.evaluate("() => document.getElementById('update-banner-text').textContent")


def test_an_installed_copy_updates_from_the_banner(e2e_server, pw_browser):
    run = [
        {'state': 'downloading', 'percent': 42, 'version': '9.9.9', 'error': None},
        {'state': 'downloading', 'percent': 42, 'version': '9.9.9', 'error': None},
        {'state': 'downloading', 'percent': 42, 'version': '9.9.9', 'error': None},
        {'state': 'downloading', 'percent': 42, 'version': '9.9.9', 'error': None},
        {'state': 'downloading', 'percent': 42, 'version': '9.9.9', 'error': None},
        {'state': 'downloading', 'percent': 42, 'version': '9.9.9', 'error': None},
        {'state': 'verifying', 'percent': 100, 'version': '9.9.9', 'error': None},
        {'state': 'ready', 'percent': 100, 'version': '9.9.9', 'error': None},
    ]
    context, pg, seen, problems = _open(pw_browser, e2e_server, CHECK, run)
    try:
        _check_for_updates(pg)
        action = pg.locator('#update-banner-action')
        assert action.is_visible() and action.text_content() == 'Update'
        assert not pg.locator('#update-banner-link').is_visible()
        assert _text(pg) == 'Version 9.9.9 is available (you have 1.7.0)'

        action.click()
        pg.wait_for_function("() => document.getElementById('update-banner-text').textContent === 'Downloading 42%'",
                             timeout=5000)
        assert pg.locator('#update-banner-progress').is_visible()
        assert pg.evaluate("() => document.getElementById('update-banner-progress-bar').style.width") == '42%'
        assert not action.is_visible()   # no second download while one runs
        # A second click on Update cannot happen: the button is gone while
        # it downloads. Check for Updates again, through the real Help menu
        # (the banner sits above the menu bar, never over it), keeps the
        # progress.
        pg.locator('#menu-bar .menu-item[data-menu="help"]').click()
        pg.locator('#menu-help .menu-option[data-action="check-updates"]').click()
        pg.wait_for_timeout(300)
        assert _text(pg).startswith('Downloading') or _text(pg) == 'Checking the download', _text(pg)

        pg.wait_for_function("() => document.getElementById('update-banner-action').textContent === 'Install and restart'"
                             " && document.getElementById('update-banner-action').style.display !== 'none'",
                             timeout=8000)
        assert _text(pg) == 'Version 9.9.9 is ready to install'
        assert not pg.locator('#update-banner-progress').is_visible()
        assert seen['download'] == 1

        # The app answers as the old version until the new one is up.
        running = {'version': '1.7.0'}
        pg.route('**/api/version', lambda r: _json(r, running))
        action.click()
        pg.wait_for_function("() => document.getElementById('update-banner-text').textContent.startsWith('Installing')",
                             timeout=5000)
        assert seen['install'] == [{'discard': False}]
        assert _text(pg) == 'Installing version 9.9.9. The app closes now and opens again when the update is done.'
        assert not action.is_visible()
        assert not pg.locator('#update-banner-dismiss').is_visible()
        assert problems == [], problems

        # The new version answers: the page comes back on it by itself.
        pg.evaluate("() => { window.__beforeUpdate = true; }")
        pg.wait_for_timeout(2500)
        assert pg.evaluate("() => window.__beforeUpdate === true")   # still the old app: no reload
        running['version'] = '9.9.9'
        pg.wait_for_function("() => !window.__beforeUpdate", timeout=10000)
    finally:
        context.close()


def test_a_refused_download_says_why_and_offers_update_again(e2e_server, pw_browser):
    run = [{'state': 'error', 'percent': 0, 'version': '9.9.9', 'error': BAD_SUM}]
    context, pg, seen, problems = _open(pw_browser, e2e_server, CHECK, run)
    try:
        _check_for_updates(pg)
        pg.locator('#update-banner-action').click()
        pg.wait_for_function("() => { const h = document.getElementById('app-toast-host');"
                             " return !!h && h.textContent.includes('did not match the release'); }", timeout=5000)
        pg.wait_for_function("() => document.getElementById('update-banner-action').textContent === 'Update'"
                             " && document.getElementById('update-banner-action').style.display !== 'none'",
                             timeout=5000)
        assert _text(pg) == 'Version 9.9.9 is available (you have 1.7.0)'
        # And the release page, which the message may point to.
        link = pg.locator('#update-banner-link')
        assert link.is_visible() and link.get_attribute('href') == CHECK['download_url']
        assert seen['install'] == []
        assert problems == [], problems
    finally:
        context.close()


LAYOUT_JS = """() => {
    const r = (sel) => { const e = document.querySelector(sel); if (!e) return null;
        const b = e.getBoundingClientRect(); return {top: b.top, bottom: b.bottom, height: b.height}; };
    const banner = document.getElementById('update-banner');
    const shown = banner.style.display !== 'none';
    const bb = banner.getBoundingClientRect();
    // Fixed-position bits pinned by measurement (fold tabs, resize strips).
    const pinned = [...document.querySelectorAll('#app *')].filter(e => {
        if (banner.contains(e)) return false;
        const cs = getComputedStyle(e);
        if (cs.position !== 'fixed' || cs.display === 'none' || cs.visibility === 'hidden') return false;
        const b = e.getBoundingClientRect();
        return b.width > 0 && b.height > 0;
    }).map(e => ({id: e.id || e.className, top: e.getBoundingClientRect().top}));
    return {
        vh: window.innerHeight, scroll: document.documentElement.scrollHeight,
        banner: shown ? {top: bb.top, bottom: bb.bottom, height: bb.height} : null,
        menu: r('#menu-bar'), status: r('#status-bar'),
        container: r('#canvas-container'), canvas: r('#main-canvas'),
        canvasPx: (() => { const c = document.getElementById('main-canvas');
            return c ? c.height / (window.devicePixelRatio || 1) : null; })(),
        pinned,
    };
}"""


@pytest.mark.parametrize(('width', 'height'), [(1600, 950), (1280, 800), (1024, 768)])
def test_the_banner_pushes_the_app_down_and_gives_it_back(e2e_server, pw_browser, width, height):
    """The banner never covers the menu bar: while it shows, the app sits
    under it, nothing hangs off the bottom, the canvas is re-measured to
    the room left; dismissed, every figure is what it was."""
    context, pg, seen, problems = _open(pw_browser, e2e_server, CHECK, [])
    try:
        pg.set_viewport_size({'width': width, 'height': height})
        pg.wait_for_timeout(600)
        before = pg.evaluate(LAYOUT_JS)
        assert before['banner'] is None and before['menu']['top'] == 0

        _check_for_updates(pg)   # through the real Help menu
        pg.wait_for_timeout(600)
        on = pg.evaluate(LAYOUT_JS)
        b = on['banner']
        assert b['top'] == 0 and b['height'] > 20, on
        assert abs(on['menu']['top'] - b['bottom']) < 1, on        # menus under it, not under it
        assert abs(on['status']['bottom'] - on['vh']) < 1, on      # the status bar still at the bottom
        assert on['scroll'] <= on['vh'], on                        # nothing pushed off the page
        shrunk = before['container']['height'] - on['container']['height']
        assert abs(shrunk - b['height']) < 1.5, (before, on)       # the canvas area gave up the banner's height
        assert on['canvas']['bottom'] <= on['container']['bottom'] + 1, on   # canvas not clipped
        assert abs(on['canvasPx'] - on['canvas']['height']) < 1.5, on        # and re-measured to it
        assert all(p['top'] >= b['bottom'] - 1 for p in on['pinned']), on['pinned']
        # The menus work with the banner up: Help opens below it.
        pg.locator('#menu-bar .menu-item[data-menu="help"]').click()
        assert pg.locator('#menu-help').is_visible()
        assert pg.locator('#menu-help').bounding_box()['y'] >= b['bottom']
        pg.keyboard.press('Escape')
        if pg.locator('#menu-help').is_visible():
            pg.locator('#menu-bar .menu-item[data-menu="help"]').click()

        pg.locator('#update-banner-dismiss').click()
        pg.wait_for_timeout(600)
        after = pg.evaluate(LAYOUT_JS)
        assert after['banner'] is None
        for key in ('menu', 'status', 'container', 'canvas'):
            for edge in ('top', 'bottom', 'height'):
                assert abs(after[key][edge] - before[key][edge]) < 1, (key, before[key], after[key])
        assert abs(after['canvasPx'] - before['canvasPx']) < 1.5
        assert problems == [], problems
    finally:
        context.close()


def test_other_copies_keep_the_download_link(e2e_server, pw_browser):
    check = dict(CHECK, can_install=False)
    context, pg, seen, problems = _open(pw_browser, e2e_server, check, [])
    try:
        _check_for_updates(pg)
        link = pg.locator('#update-banner-link')
        assert link.is_visible() and link.text_content() == 'Download'
        assert link.get_attribute('href') == CHECK['download_url']
        assert not pg.locator('#update-banner-action').is_visible()
        assert not pg.locator('#update-banner-progress').is_visible()
        assert seen['download'] == 0
        assert problems == [], problems
    finally:
        context.close()
