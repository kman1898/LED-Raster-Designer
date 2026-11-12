"""The start page's New over unsaved edits, and the first-run guide (1.6.0).

  - New on the start page over a show with unsaved edits closed the page
    before "Save changes?" came up, so Cancel (or Esc) left no start page.
    It stays up behind the question now, as Open file… and a Recent file
    already did; Don't Save still goes on to the new project's picker.
  - The first-run guide runs on the first run only (the owner,
    2026-11-04). Nothing recorded a first run: only an opt-out box in the
    guide kept it away, so it came back every launch, and a launch quit
    in the middle of it opened on the start page next (the guide's
    recovery skips it), so the two took turns. Every launch after the
    first opens on the start page. A browser that ran an older build (it
    has a What's New stamp) is past its first run.
  - The opt-out box is gone (owner, 2026-11-04: "Remove it"), and the key
    it wrote is ignored: an old browser that still holds it neither keeps
    a first run away nor breaks anything.

A launch is a new browser tab (app-start-page.js). An automated browser
never sees the guide, the start page or the unsaved question unless a test
asks: the first-run tests here run as a real browser does
(navigator.webdriver reads false), the New tests set the documented
window flags.

The host's save, open and folder dialogs are stubbed to answer cancelled,
so no real dialog can open.

Run locally (each session takes its own free port):
    python -m pytest tests/test_start_page_new_and_first_run.py -v --browser chromium
"""

import json
import urllib.request

import pytest

from conftest import new_server_run

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project and preferences the way this module
    found them (the guide's scratch show and its Preferences)."""


QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
ASK = QUIET + "window.__lrdStartPage = true; window.__lrdAskUnsaved = true;"
# A real browser: no navigator.webdriver, so the launch UI comes up as it
# does for a person.
REAL = "Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => false, configurable: true });"

FIRST_RUN_KEY = 'lrd_quickstart_first_run_done'
STASH_KEY = 'lrd_tour_saved_world'


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _new_pristine_project(url):
    req = urllib.request.Request(url + '/api/project/new', data=b'', method='POST')
    with _opener().open(req, timeout=10) as reply:
        assert reply.status == 200


def _server_json(url, path):
    with _opener().open(url + path, timeout=10) as reply:
        return json.loads(reply.read().decode('utf-8'))


def _route_dialogs(target):
    """The host's file and folder dialogs answer cancelled."""
    body = json.dumps({'ok': False, 'cancelled': True})
    for name in ('save-file', 'open-file', 'select-directory'):
        target.route(f'**/api/native-dialog/{name}',
                     lambda route: route.fulfill(status=200, content_type='application/json', body=body))


def _context(pw_browser, init):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(init)
    _route_dialogs(context)
    return context


def _launch(context):
    """A launch: the app started, its first page a new tab. The start page
    is once per server run (owner, 2026-11-09), and the e2e server is one
    run, so each launch here starts a new run. Returns (page, problems)."""
    new_server_run()
    pg = context.new_page()
    problems = []
    pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))
    pg.goto(context._lrd_url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    return pg, problems


def _start_up(pg):
    return pg.evaluate("() => window.app.startPageOpen()")


def _wait_start(pg, timeout=15000):
    pg.wait_for_function("() => window.app.startPageOpen()", timeout=timeout)


def _guide_visible(pg):
    return pg.evaluate("() => { const q = window.QuickStart; try { return !!(q && q.state().visible); }"
                       " catch (e) { return false; } }")


def _asked(pg):
    pg.wait_for_selector('#unsaved-changes-modal', state='visible', timeout=5000)


def _answer(pg, label):
    pg.locator('#unsaved-changes-modal .app-ask-buttons button', has_text=label).first.click()
    pg.wait_for_function("() => !document.getElementById('unsaved-changes-modal')", timeout=5000)


# ── the start page's New over unsaved edits ───────────────────────────────

def _guide_show_seed(url):
    """A launch after quitting mid-guide: the person's show comes back
    from the guide's stash (never saved as it stands, so unsaved), and the
    start page stands over it with no startup screen under it."""
    _new_pristine_project(url)
    proj = _server_json(url, '/api/project')
    proj.pop('is_pristine', None)
    proj['name'] = 'Kept Show'
    stash = {'project': proj, 'mode': 'pixel-map', 'sheets': [], 'prefs': None, 'tray': None,
             'panels': None, 'layout': None, 'currentLayerId': None, 'at': 0}
    return ("try{if(!sessionStorage.getItem('__stash')){sessionStorage.setItem('__stash','1');"
            f"localStorage.setItem('{STASH_KEY}', " + json.dumps(json.dumps(stash)) + ");}}catch(e){}")


def _start_page_over_unsaved_show(e2e_server, pw_browser):
    context = _context(pw_browser, ASK + _guide_show_seed(e2e_server))
    context._lrd_url = e2e_server
    pg, problems = _launch(context)
    _wait_start(pg)
    assert pg.evaluate("() => [window.app.project.name, window.app._startupTargetId,"
                       " window.app.projectHasUnsavedChanges()]") == ['Kept Show', None, True]
    return context, pg, problems


def test_cancel_on_save_changes_leaves_the_start_page_up(e2e_server, pw_browser):
    context = None
    try:
        context, pg, problems = _start_page_over_unsaved_show(e2e_server, pw_browser)
        pg.locator('#start-page-new').click()
        _asked(pg)
        # the page stands behind the question
        assert _start_up(pg)
        _answer(pg, 'Cancel')
        pg.wait_for_timeout(300)
        assert _start_up(pg)
        assert pg.evaluate("() => window.app.project.name") == 'Kept Show'
        # and New asks again from it; Esc answers the question only
        pg.locator('#start-page-new').click()
        _asked(pg)
        pg.keyboard.press('Escape')
        pg.wait_for_function("() => !document.getElementById('unsaved-changes-modal')", timeout=5000)
        pg.wait_for_timeout(300)
        assert _start_up(pg)
        assert pg.evaluate("() => window.app.project.name") == 'Kept Show'
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_dont_save_goes_on_to_the_new_project(e2e_server, pw_browser):
    context = None
    try:
        context, pg, problems = _start_page_over_unsaved_show(e2e_server, pw_browser)
        pg.locator('#start-page-new').click()
        _asked(pg)
        _answer(pg, "Don't Save")
        pg.wait_for_function("() => window.app.project.name === 'Untitled Project'", timeout=10000)
        pg.wait_for_function("() => !window.app.startPageOpen()", timeout=5000)
        assert problems == [], problems
    finally:
        if context:
            context.close()


# ── the first-run guide, on the first run only ────────────────────────────

def _real_context(pw_browser, url, seed=''):
    context = _context(pw_browser, REAL + seed)
    context._lrd_url = url
    return context


def _ls(pg, key):
    return pg.evaluate("(k) => localStorage.getItem(k)", key)


def test_the_guide_shows_on_the_first_launch_only(e2e_server, pw_browser):
    """First launch: the guide. Quit in the middle of it: the next launch
    puts the show back and opens on the start page. Every launch after
    that opens on the start page too (the guide came back here before)."""
    _new_pristine_project(e2e_server)
    context = None
    try:
        context = _real_context(pw_browser, e2e_server)
        first, problems = _launch(context)
        first.wait_for_function("() => { const q = window.QuickStart; return !!(q && q.state().visible); }",
                                timeout=20000)
        assert not _start_up(first)
        # quit in the middle of it: the stash stays behind
        first.wait_for_function(f"() => !!localStorage.getItem('{STASH_KEY}')", timeout=10000)
        first.close()
        assert problems == [], problems

        second, problems = _launch(context)
        _wait_start(second, 20000)
        assert not _guide_visible(second)
        assert _ls(second, STASH_KEY) is None
        second.close()
        assert problems == [], problems

        for _ in range(2):
            pg, problems = _launch(context)
            _wait_start(pg, 20000)
            assert not _guide_visible(pg)
            pg.wait_for_timeout(1500)
            assert not _guide_visible(pg)
            assert _start_up(pg)
            assert _ls(pg, FIRST_RUN_KEY) == '1'
            pg.close()
            assert problems == [], problems
    finally:
        if context:
            context.close()


def test_a_finished_first_run_guide_never_comes_back(e2e_server, pw_browser):
    """Skip the first-run guide: the start page follows it, and the next
    launch opens on the start page. The guide's callout has no opt-out
    box, and Help still opens the guide."""
    _new_pristine_project(e2e_server)
    context = None
    try:
        context = _real_context(pw_browser, e2e_server)
        first, problems = _launch(context)
        first.wait_for_function("() => { const q = window.QuickStart; return !!(q && q.state().visible); }",
                                timeout=20000)
        first.wait_for_selector('#qs-skip', state='visible', timeout=10000)
        callout = first.evaluate("""() => { const c = document.getElementById('qs-callout');
            return { box: !!c.querySelector('input[type=checkbox]'), text: c.textContent }; }""")
        assert callout['box'] is False, callout
        assert 'show on startup' not in callout['text'].lower(), callout
        first.locator('#qs-skip').click()
        _wait_start(first, 20000)
        assert not _guide_visible(first)
        first.close()
        nxt, problems2 = _launch(context)
        _wait_start(nxt, 20000)
        assert not _guide_visible(nxt)
        assert _ls(nxt, FIRST_RUN_KEY) == '1'
        # Help > Guides > Quick Start still opens it
        nxt.keyboard.press('Escape')
        nxt.wait_for_function("() => !window.app.startPageOpen()", timeout=5000)
        nxt.locator('#menu-bar .menu-item[data-menu="help"]').click()
        nxt.locator('#menu-help .menu-option[data-action="guides"]').hover()
        nxt.locator('#guides-submenu .menu-option[data-action="quick-start"]').click()
        nxt.wait_for_function("() => { const q = window.QuickStart; return !!(q && q.state().visible); }",
                              timeout=20000)
        nxt.wait_for_selector('#qs-skip', state='visible', timeout=10000)
        nxt.locator('#qs-skip').click()
        nxt.wait_for_function("() => !window.QuickStart.state().visible && !window.QuickStart.state().running",
                              timeout=30000)
        nxt.close()
        assert problems == [] and problems2 == [], (problems, problems2)
    finally:
        if context:
            context.close()


def test_a_browser_that_ran_an_older_build_is_past_its_first_run(e2e_server, pw_browser):
    """An update: this browser has a What's New stamp (the version it ran)
    and no first-run mark. Its first launch of this build opens on the
    start page, never the first-run guide."""
    _new_pristine_project(e2e_server)
    version = _server_json(e2e_server, '/api/version')['version']
    seed = ("try{if(!sessionStorage.getItem('__seed')){sessionStorage.setItem('__seed','1');"
            f"localStorage.setItem('lrd_whatsnew_seen', {json.dumps(version)});"
            "localStorage.setItem('lrd_whatsnew_full', '1');}}catch(e){}")
    context = None
    try:
        context = _real_context(pw_browser, e2e_server, seed)
        pg, problems = _launch(context)
        _wait_start(pg, 20000)
        assert not _guide_visible(pg)
        assert _ls(pg, FIRST_RUN_KEY) == '1'
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_the_retired_opt_out_key_is_ignored(e2e_server, pw_browser):
    """The key the removed opt-out box wrote ('1' = never auto-show) means
    nothing now: on a first run the guide still opens, and nothing breaks
    on it."""
    _new_pristine_project(e2e_server)
    seed = ("try{if(!sessionStorage.getItem('__seed')){sessionStorage.setItem('__seed','1');"
            "localStorage.setItem('lrd_quickstart_' + 'disabled', '1');}}catch(e){}")
    context = None
    try:
        context = _real_context(pw_browser, e2e_server, seed)
        pg, problems = _launch(context)
        pg.wait_for_function("() => { const q = window.QuickStart; return !!(q && q.state().visible); }",
                             timeout=20000)
        assert _ls(pg, FIRST_RUN_KEY) == '1'
        pg.wait_for_selector('#qs-skip', state='visible', timeout=10000)
        pg.locator('#qs-skip').click()
        _wait_start(pg, 20000)
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_the_guide_code_never_reads_the_retired_key():
    import os
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src', 'static', 'js')
    for name in ('quickstart.js', 'whatsnew.js', 'whatsnew_content.js'):
        with open(os.path.join(root, name), encoding='utf-8') as fh:
            src = fh.read()
        assert "getItem('lrd_quickstart_disabled')" not in src, name
        assert "setItem('lrd_quickstart_disabled'" not in src, name
        assert "'lrd_quickstart_disabled'" not in src, name
        assert 'qs-nolaunch' not in src, name
        assert 'show on startup' not in src.lower(), name


def test_an_automated_browser_still_never_sees_the_guide(e2e_server, pw_browser):
    """navigator.webdriver: no first-run guide, and the first run is not
    marked done, so a test that later runs as a real browser in the same
    profile still gets its first run."""
    _new_pristine_project(e2e_server)
    context = None
    try:
        context = _context(pw_browser, '')
        context._lrd_url = e2e_server
        pg, problems = _launch(context)
        pg.wait_for_function("() => window.QuickStart && !window.QuickStart.autoPending()", timeout=20000)
        pg.wait_for_timeout(800)
        assert not _guide_visible(pg)
        assert not _start_up(pg)
        assert _ls(pg, FIRST_RUN_KEY) != '1'
        assert problems == [], problems
    finally:
        if context:
            context.close()
