"""A page where the app never started says so (owner, 2026-11-12).

When some of the app's scripts cannot be fetched (a bad network, a server
under load) or one throws while starting, the app object is never made. The
page still looked normal, because theme.js sizes the panels and drag strips
on its own, but nothing on it worked and nothing said why (commit b83dcecb
traced two test failures to exactly this). Now the page says "The app
didn't finish loading." with a Reload button that reloads it.

The guard is the first script in index.html, inline, because the scripts
that failed cannot host it. Its proof is the load order: every module
script runs or fails before DOMContentLoaded, and main.js makes the app in
its DOMContentLoaded handler, then calls lrdAppStarted(). A slow load only
moves that event later, so a slow load that succeeds never shows the
notice. Its one backstop is a load that stops getting anywhere: no request
finishing for LRD_BOOT_STALL_S seconds (30 in the app) before the event.

Run locally:
    python -m pytest tests/test_app_not_started.py -v --browser chromium
"""

import os
import re
import time

import pytest

JS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'src', 'static', 'js')

NOTICE_TEXT = "The app didn't finish loading."
QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
# The notice ever appearing, however briefly, is recorded by the page.
WATCH = """
window.__lrdNoticeSeen = 0;
new MutationObserver(function () {
    if (document.getElementById('app-not-started')) window.__lrdNoticeSeen += 1;
}).observe(document, { childList: true, subtree: true });
"""
STARTED_JS = "() => !!(window.app && !(window.app instanceof Node) && window.app.project !== undefined)"


@pytest.fixture
def ctx(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1400, 'height': 860})
    context.add_init_script(QUIET)
    context.add_init_script(WATCH)
    yield context
    context.close()


def _js(name):
    return f'**/static/js/{name}'


def _logged(page):
    """The app_not_started lines the page sent to /api/log."""
    lines = []

    def on_request(req):
        if req.url.endswith('/api/log') and req.method == 'POST':
            body = req.post_data or ''
            if 'app_not_started' in body:
                lines.append(body)
    page.on('request', on_request)
    return lines


def _expect_notice(page, timeout=15000):
    page.wait_for_selector('#app-not-started', state='visible', timeout=timeout)
    text = page.locator('#app-not-started-text').inner_text()
    assert text == NOTICE_TEXT, text
    assert page.locator('#app-not-started-reload').inner_text() == 'Reload'
    assert not page.evaluate(STARTED_JS), 'the notice showed on a page whose app started'


def _expect_no_notice(page):
    page.wait_for_function(STARTED_JS, timeout=30000)
    page.wait_for_timeout(1500)
    assert page.locator('#app-not-started').count() == 0
    assert page.evaluate('window.__lrdNoticeSeen') == 0, 'the notice showed for a moment'


# ── Failing loads say so ─────────────────────────────────────────────────

# main.js is the module script itself, app-core.js and app-colors.js are
# imports of it, and canvas.js is a classic script the app's constructor
# needs: without it the constructor throws and the app is never made.
@pytest.mark.parametrize('name,how', [
    ('main.js', 'abort'),
    ('app-core.js', '404'),
    ('app-colors.js', 'abort'),
    ('canvas.js', '404'),
])
def test_a_script_that_does_not_load_shows_the_notice(ctx, e2e_server, name, how):
    page = ctx.new_page()
    logged = _logged(page)
    if how == 'abort':
        page.route(_js(name), lambda route: route.abort())
    else:
        page.route(_js(name), lambda route: route.fulfill(status=404, body='not found'))
    page.goto(e2e_server, wait_until='domcontentloaded')
    _expect_notice(page)
    # The reason reaches the app's log, naming the script. A failed import
    # fails its module script, so the browser blames main.js for it.
    page.wait_for_timeout(500)
    blamed = name if name in ('main.js', 'canvas.js') else 'main.js or one of its imports'
    assert logged and any(blamed in line for line in logged), logged


def test_a_module_that_throws_while_starting_shows_the_notice(ctx, e2e_server):
    page = ctx.new_page()
    page.route(_js('app-colors.js'), lambda route: route.fulfill(
        status=200, content_type='application/javascript',
        body="throw new Error('a module failed while starting');"))
    page.goto(e2e_server, wait_until='domcontentloaded')
    _expect_notice(page)


def test_reload_reloads_the_page_and_the_app_starts(ctx, e2e_server):
    page = ctx.new_page()
    page.route(_js('app-core.js'), lambda route: route.abort())
    page.goto(e2e_server, wait_until='domcontentloaded')
    _expect_notice(page)
    assert page.evaluate('document.activeElement && document.activeElement.id') == \
        'app-not-started-reload', 'Reload is not focused, so Enter does not reload'
    page.unroute(_js('app-core.js'))
    page.evaluate('window.__lrdBefore = 1')
    with page.expect_navigation(wait_until='domcontentloaded'):
        page.locator('#app-not-started-reload').click()
    assert page.evaluate('window.__lrdBefore') is None, 'the page did not reload'
    _expect_no_notice(page)


def test_a_load_that_stops_getting_anywhere_shows_the_notice(ctx, e2e_server):
    """The backstop: a script whose request never answers holds the page
    before DOMContentLoaded forever. The app waits 30 seconds with nothing
    finishing; this page is told 3."""
    ctx.add_init_script('window.LRD_BOOT_STALL_S = 3;')
    page = ctx.new_page()
    page.route(_js('app-core.js'), lambda route: None)   # never answered
    page.goto(e2e_server, wait_until='commit')
    _expect_notice(page, timeout=20000)


# ── Loads that work never show it ─────────────────────────────────────────

def test_a_normal_load_shows_no_notice(ctx, e2e_server):
    page = ctx.new_page()
    page.goto(e2e_server, wait_until='domcontentloaded')
    _expect_no_notice(page)
    assert page.evaluate('typeof window.lrdAppStarted') == 'function'


def test_a_slow_load_that_succeeds_shows_no_notice(ctx, e2e_server):
    """Scripts held back by seconds each, the way a slow PC or the desktop
    app's cold start feels, with the backstop cut to 5 seconds: the load
    takes far longer than that, but something finishes every 1.5 seconds,
    so the page waits for the app."""
    ctx.add_init_script('window.LRD_BOOT_STALL_S = 5;')
    page = ctx.new_page()
    slow = ['main.js', 'app-core.js', 'app-server-link.js', 'app-colors.js',
            'app-network.js', 'helpers.js']

    def hold(route):
        time.sleep(1.5)
        route.continue_()
    for name in slow:
        page.route(_js(name), hold)
    started = time.monotonic()
    page.goto(e2e_server, wait_until='commit')
    _expect_no_notice(page)
    assert time.monotonic() - started > 7, 'the scripts were not held back'


# ── What the guard leans on ───────────────────────────────────────────────

def test_main_js_tells_the_guard_the_app_started():
    with open(os.path.join(JS_DIR, 'main.js'), encoding='utf-8') as f:
        src = f.read()
    made = src.index('window.app = new LEDRasterApp();')
    told = src.index('window.lrdAppStarted()')
    assert made < told, 'main.js must make the app before it tells the guard'


def test_no_app_module_awaits_at_the_top_level():
    """The guard decides right after DOMContentLoaded. A module that awaits
    at its top level lets that event fire before the app is made, and every
    normal load would show the notice."""
    offenders = []
    for name in sorted(os.listdir(JS_DIR)):
        if not name.endswith('.js'):
            continue
        with open(os.path.join(JS_DIR, name), encoding='utf-8') as f:
            for n, line in enumerate(f, 1):
                if re.match(r'(?:export\s+)?(?:(?:const|let|var)\s[^=]*=\s*)?await\b', line):
                    offenders.append(f'{name}:{n}: {line.strip()}')
    assert not offenders, offenders
