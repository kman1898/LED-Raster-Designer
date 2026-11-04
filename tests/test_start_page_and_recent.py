"""The start page and Recent Files that read the file (1.6.0).

Owner, 2026-11-03: on launch the app first shows a start page: New
project, Open file…, and the Recent list. New opens the panel picker (and
the picker's Cancel comes back to the start page), Open file… is File >
Open, a recent file opens the show, and X or Esc leaves an empty project.
File > New skips the start page and goes straight to the picker.

And the bug report: "my recent projects aren't loading the file that I
last saved. They're loading an earlier version." Recent Files kept a copy
of every show in localStorage and reopened the copy. On the Mac a full
localStorage made the update throw after the file was written (so the
copy froze at an old version, and File > Open was logged as failed), a
show saved on the other machine opened as this machine's copy, two files
of one name shared one entry, and a cancelled save still updated it. Now
an entry with a known path keeps the path and reopening reads the file
(the host's read-file route), through File > Open's own code.

The native dialog routes are stubbed per page (save-file and open-file
answer a path in tmp_path); write-file and read-file run for real. Every
other native-dialog request is refused, so no real dialog can open.

Run locally (each session takes its own free port):
    python -m pytest tests/test_start_page_and_recent.py -v --browser chromium
"""

import json
import os
import urllib.request

import pytest

from conftest import settled

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found them."""


QUIET = "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
START_PAGE = QUIET + "window.__lrdStartPage = true;"
BOTH = START_PAGE + "window.__lrdStartupPicker = true;"
# The client log, as sendClientLog beacons it, kept on the page.
CLIENT_LOG = (
    "window.__clog = [];"
    "(function () { const send = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);"
    " navigator.sendBeacon = (u, b) => { try { b.text().then(t => { const j = JSON.parse(t);"
    " window.__clog.push({ action: j.action, details: j.details }); }); } catch (e) {}"
    " return send ? send(u, b) : true; }; })();"
)


def _new_pristine_project(url):
    """What a launch finds: the server's fresh project (New)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url + '/api/project/new', data=b'', method='POST')
    with opener.open(req, timeout=10) as reply:
        assert reply.status == 200


class Dialogs:
    """Stubbed host dialogs: what Save and Open answer next."""

    def __init__(self):
        self.save_answer = None
        self.open_answer = None
        self.calls = []

    def route(self, page):
        def handler(route):
            url = route.request.url
            name = url.rsplit('/', 1)[-1]
            self.calls.append(name)
            if name == 'available':
                return route.fulfill(status=200, content_type='application/json',
                                     body=json.dumps({'ok': True, 'host': True}))
            if name in ('save-file', 'open-file'):
                answer = self.save_answer if name == 'save-file' else self.open_answer
                if answer is None:
                    answer = {'ok': False, 'cancelled': False, 'unavailable': True}
                elif isinstance(answer, str):
                    answer = {'ok': True, 'path': answer}
                return route.fulfill(status=200, content_type='application/json',
                                     body=json.dumps(answer))
            if name in ('write-file', 'read-file'):
                return route.continue_()
            return route.fulfill(status=403, content_type='application/json',
                                 body=json.dumps({'ok': False}))
        page.route('**/api/native-dialog/**', handler)


def _open_page(pw_browser, url, init=QUIET, recent=None, dialogs=None):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(CLIENT_LOG + init)
    if recent is not None:
        # Seeded once per tab, before the app reads it.
        context.add_init_script(
            "try{if(!sessionStorage.getItem('__seeded')){sessionStorage.setItem('__seeded','1');"
            "localStorage.setItem('ledRasterRecentFiles', " + json.dumps(json.dumps(recent)) + ");}}"
            "catch(e){}")
    pg = context.new_page()
    problems = []
    pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))
    pg.on('console', lambda m: problems.append('console: ' + m.text)
          if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
    pg.on('response', lambda r: problems.append(f'{r.status} {r.url}')
          if '/api/' in r.url and r.status >= 400 and '/api/native-dialog/' not in r.url
          and '/api/panel-catalog/refresh' not in r.url else None)
    (dialogs or Dialogs()).route(pg)
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    return context, pg, problems


def _start_up(pg):
    return pg.evaluate("() => { const m = document.getElementById('start-page-modal');"
                       " return !!m && m.style.display === 'block'; }")


def _wait_start(pg, timeout=10000):
    pg.wait_for_function("() => { const m = document.getElementById('start-page-modal');"
                         " return !!m && m.style.display === 'block'; }", timeout=timeout)


def _picker_up(pg):
    return pg.evaluate("() => document.getElementById('preset-picker-modal').style.display === 'block'"
                       " && window.app._pickerMode === 'startup'")


def _wait_picker(pg, timeout=10000):
    pg.wait_for_function("() => document.getElementById('preset-picker-modal').style.display === 'block'"
                         " && window.app._pickerMode === 'startup'", timeout=timeout)


def _menu(pg, action):
    pg.locator('#menu-bar .menu-item[data-menu="file"]').click()
    pg.wait_for_timeout(150)
    pg.locator(f'#menu-file .menu-option[data-action="{action}"]').click()


def _open_recent_menu(pg, idx):
    pg.locator('#menu-bar .menu-item[data-menu="file"]').click()
    pg.wait_for_timeout(150)
    pg.locator('#menu-file .menu-option[data-action="recent-files"]').hover()
    pg.wait_for_timeout(250)
    pg.locator('#recent-files-list .menu-option').nth(idx).click()


def _recent(pg):
    return pg.evaluate("() => JSON.parse(localStorage.getItem('ledRasterRecentFiles') || '[]')")


def _set_columns(pg, n):
    box = pg.locator('#screen-columns')
    box.click()
    box.fill(str(n))
    box.press('Enter')
    pg.wait_for_function("(n) => window.app.project.layers[0].columns === n", arg=n, timeout=5000)
    pg.wait_for_timeout(300)


def _columns(pg):
    return pg.evaluate("() => window.app.project.layers[0].columns")


def _file_columns(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)['layers'][0]['columns']


def _client_log(pg, action=None):
    log = pg.evaluate("() => window.__clog")
    return [e for e in log if action is None or e['action'] == action]


def _show_file(pg, path, name, columns, screens=1):
    """A show on disk, made from the server's own project shape."""
    proj = pg.evaluate("async () => (await fetch('/api/project')).json()")
    layer = next(l for l in proj['layers'] if (l.get('type') or 'screen') == 'screen')
    proj['layers'] = [dict(layer, id=i + 1, name=f'Screen{i + 1}', columns=columns) for i in range(screens)]
    proj['name'] = name
    proj.pop('is_pristine', None)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(proj, fh)


# ── the start page ────────────────────────────────────────────────────────

def test_launch_opens_the_start_page(e2e_server, pw_browser):
    context, pg, problems = None, None, []
    try:
        _new_pristine_project(e2e_server)
        context, pg, problems = _open_page(pw_browser, e2e_server, init=START_PAGE)
        _wait_start(pg)
        page = pg.evaluate("""() => ({
            title: document.getElementById('start-page-title').textContent,
            buttons: [...document.querySelectorAll('#start-page-modal .start-page-actions button')].map(b => b.textContent),
            recent: document.getElementById('start-page-recent').textContent,
            screens: window.app.project.layers.length,
        })""")
        assert page == {'title': 'LED Raster Designer', 'buttons': ['New project', 'Open file…'],
                        'recent': 'No recent files', 'screens': 1}, page
        assert not pg.evaluate("() => document.getElementById('preset-picker-modal').style.display === 'block'")
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_new_opens_the_picker_its_cancel_comes_back_and_esc_leaves_an_empty_project(e2e_server, pw_browser):
    context, pg, problems = None, None, []
    try:
        _new_pristine_project(e2e_server)
        context, pg, problems = _open_page(pw_browser, e2e_server, init=START_PAGE)
        _wait_start(pg)
        startup_id = pg.evaluate("() => window.app.project.layers[0].id")
        # New -> the panel picker, the start page gone
        pg.locator('#start-page-new').click()
        _wait_picker(pg)
        assert not _start_up(pg)
        assert pg.locator('#preset-picker-title').text_content() == 'Choose a panel'
        assert pg.locator('#preset-picker-subtitle').text_content().endswith(
            'Cancel goes back to the start page.')
        # Cancel -> back to the start page, the startup screen still there
        pg.locator('#preset-picker-cancel').click()
        _wait_start(pg, 5000)
        assert not _picker_up(pg)
        assert pg.evaluate("() => window.app.project.layers.map(l => l.id)") == [startup_id]
        # ...and New again still works
        pg.locator('#start-page-new').click()
        _wait_picker(pg)
        pg.locator('#preset-picker-cancel').click()
        _wait_start(pg, 5000)
        # Esc -> an empty project, nothing up
        pg.keyboard.press('Escape')
        pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
        pg.wait_for_timeout(500)
        assert not _start_up(pg) and not _picker_up(pg)
        srv = pg.evaluate("async () => (await fetch('/api/project')).json()")
        assert srv['layers'] == [], srv['layers']
        assert pg.evaluate("() => window.app.history.length") == 1
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_the_close_button_leaves_an_empty_project(e2e_server, pw_browser):
    context, pg, problems = None, None, []
    try:
        _new_pristine_project(e2e_server)
        context, pg, problems = _open_page(pw_browser, e2e_server, init=START_PAGE)
        _wait_start(pg)
        pg.locator('#start-page-close').click()
        pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
        assert not _start_up(pg)
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_file_new_goes_straight_to_the_picker(e2e_server, pw_browser):
    context, pg, problems = None, None, []
    try:
        _new_pristine_project(e2e_server)
        context, pg, problems = _open_page(pw_browser, e2e_server, init=BOTH)
        _wait_start(pg)
        pg.keyboard.press('Escape')
        pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
        _menu(pg, 'new')
        _wait_picker(pg)
        pg.wait_for_timeout(800)
        assert not _start_up(pg)
        assert pg.locator('#preset-picker-subtitle').text_content().endswith('Cancel starts with no screens.')
        # its Cancel keeps today's result: an empty project, no start page
        pg.locator('#preset-picker-cancel').click()
        pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
        pg.wait_for_timeout(600)
        assert not _start_up(pg) and not _picker_up(pg)
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_a_recent_file_on_the_start_page_opens_the_show(e2e_server, pw_browser, tmp_path):
    context, pg, problems = None, None, []
    show = str(tmp_path / 'Start Page Show.json')
    try:
        _new_pristine_project(e2e_server)
        recent = [{'name': 'Start Page Show', 'path': show, 'timestamp': 1700000000000, 'screenCount': 1}]
        context, pg, problems = _open_page(pw_browser, e2e_server, init=START_PAGE, recent=recent)
        _wait_start(pg)
        _show_file(pg, show, 'Start Page Show', columns=7, screens=2)
        rows = pg.evaluate("() => [...document.querySelectorAll('#start-page-recent .start-page-recent-row')]"
                           ".map(r => [r.querySelector('.start-page-recent-name').textContent,"
                           " r.querySelector('.start-page-recent-detail').textContent, r.title])")
        assert len(rows) == 1 and rows[0][0] == 'Start Page Show' and rows[0][2] == show, rows
        assert rows[0][1].endswith('· 1 screen'), rows
        pg.locator('#start-page-recent .start-page-recent-row').first.click()
        pg.wait_for_function("() => window.app.project.name === 'Start Page Show'"
                             " && window.app.project.layers.length === 2", timeout=10000)
        pg.wait_for_timeout(800)
        assert not _start_up(pg)
        assert _columns(pg) == 7
        srv = pg.evaluate("async () => (await fetch('/api/project')).json()")
        assert srv['name'] == 'Start Page Show' and len(srv['layers']) == 2
        entry = _recent(pg)[0]
        assert entry['path'] == show and entry['screenCount'] == 2 and 'data' not in entry, entry
        assert entry['timestamp'] > 1700000000000
        assert _client_log(pg, 'load_project_file_error') == []
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_open_file_on_the_start_page_opens_through_the_host_dialog(e2e_server, pw_browser, tmp_path):
    """Open file… is File > Open: the host's Open dialog picks the file,
    the server reads it, and Recent keeps its path. A cancel leaves the
    start page up."""
    context, pg, problems = None, None, []
    show = str(tmp_path / 'Opened Show.json')
    dialogs = Dialogs()
    try:
        _new_pristine_project(e2e_server)
        context, pg, problems = _open_page(pw_browser, e2e_server, init=START_PAGE, dialogs=dialogs)
        _wait_start(pg)
        _show_file(pg, show, 'Opened Show', columns=9)
        dialogs.open_answer = {'ok': False, 'cancelled': True, 'unavailable': False}
        pg.locator('#start-page-open').click()
        pg.wait_for_timeout(800)
        assert _start_up(pg) and pg.evaluate("() => window.app.project.layers.length") == 1
        dialogs.open_answer = show
        pg.locator('#start-page-open').click()
        pg.wait_for_function("() => window.app.project.name === 'Opened Show'", timeout=10000)
        pg.wait_for_timeout(800)
        assert not _start_up(pg)
        assert _columns(pg) == 9
        assert [(e['path'], 'data' in e) for e in _recent(pg)] == [(show, False)]
        assert problems == [], problems
    finally:
        if context:
            context.close()


# ── Recent Files read the file ────────────────────────────────────────────

def test_reopening_from_recent_gives_the_last_save(e2e_server, pw_browser, tmp_path):
    """The reported bug: save, save again, reopen from Recent -> the
    second save. And a file saved since by another machine (changed on
    disk) reopens as it is on disk, not as this browser last saw it."""
    context, pg, problems = None, None, []
    show = str(tmp_path / 'Round Trip.json')
    dialogs = Dialogs()
    dialogs.save_answer = show
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, dialogs=dialogs)
        pg.evaluate("() => { window.app.project.name = 'Round Trip'; }")
        _set_columns(pg, 5)
        _menu(pg, 'save')
        pg.wait_for_function("() => document.getElementById('status-message').textContent === 'Project saved to file'",
                             timeout=10000)
        assert _file_columns(show) == 5
        _set_columns(pg, 9)
        _menu(pg, 'save')
        pg.wait_for_function("(p) => JSON.parse(localStorage.getItem('ledRasterRecentFiles') || '[]').length === 1",
                             arg=show, timeout=10000)
        pg.wait_for_timeout(500)
        assert _file_columns(show) == 9
        entries = _recent(pg)
        assert [(e['path'], e['name'], e['screenCount'], 'data' in e) for e in entries] == [
            (show, 'Round Trip', 1, False)], entries
        _set_columns(pg, 3)
        _open_recent_menu(pg, 0)
        pg.wait_for_function("() => window.app.project.layers[0].columns === 9", timeout=10000)
        pg.wait_for_timeout(600)
        # the menu row: the file's name, "1 screen"
        _menu_rows = pg.evaluate("() => [...document.querySelectorAll('#recent-files-list .recent-file-item')]"
                                 ".map(e => [e.querySelector('.recent-file-name').textContent,"
                                 " e.querySelector('.recent-file-date').textContent])")
        assert _menu_rows[0][0] == 'Round Trip' and _menu_rows[0][1].endswith('· 1 screen'), _menu_rows
        # another machine saves the file
        with open(show, encoding='utf-8') as fh:
            data = json.load(fh)
        data['layers'][0]['columns'] = 12
        with open(show, 'w', encoding='utf-8') as fh:
            json.dump(data, fh)
        _open_recent_menu(pg, 0)
        pg.wait_for_function("() => window.app.project.layers[0].columns === 12", timeout=10000)
        pg.wait_for_timeout(600)
        assert pg.evaluate("async () => (await (await fetch('/api/project')).json()).layers[0].columns") == 12
        assert 'read-file' in dialogs.calls
        assert _client_log(pg, 'load_project_file_error') == []
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_a_cancelled_save_leaves_recent_unchanged(e2e_server, pw_browser, tmp_path):
    context, pg, problems = None, None, []
    dialogs = Dialogs()
    dialogs.save_answer = {'ok': False, 'cancelled': True, 'unavailable': False}
    before = [{'name': 'Earlier Show', 'path': str(tmp_path / 'Earlier Show.json'),
               'timestamp': 1700000000000, 'screenCount': 2}]
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, dialogs=dialogs, recent=before)
        pg.evaluate("() => { window.app.project.name = 'Earlier Show'; }")
        result = pg.evaluate("() => window.app.saveProjectToFile()")
        assert result == {'saved': False, 'cancelled': True, 'path': None, 'how': 'native'}, result
        pg.wait_for_timeout(300)
        assert _recent(pg) == before
        assert pg.locator('#status-message').text_content() != 'Project saved to file'
        assert 'write-file' not in dialogs.calls
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_two_files_of_one_name_are_two_entries(e2e_server, pw_browser, tmp_path):
    context, pg, problems = None, None, []
    (tmp_path / 'Tour').mkdir()
    (tmp_path / 'Backup').mkdir()
    a = str(tmp_path / 'Tour' / 'Same Name.json')
    b = str(tmp_path / 'Backup' / 'Same Name.json')
    dialogs = Dialogs()
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, dialogs=dialogs)
        pg.evaluate("() => { window.app.project.name = 'Same Name'; }")
        _set_columns(pg, 4)
        dialogs.save_answer = a
        assert pg.evaluate("() => window.app.saveProjectToFile()")['path'] == a
        _set_columns(pg, 6)
        dialogs.save_answer = b
        assert pg.evaluate("() => window.app.saveProjectToFile()")['path'] == b
        assert [e['path'] for e in _recent(pg)] == [b, a]
        labels = pg.evaluate("() => [...document.querySelectorAll('#recent-files-list .recent-file-name')]"
                             ".map(e => e.textContent)")
        assert labels == ['Same Name (Backup)', 'Same Name (Tour)'], labels
        # each opens its own file
        pg.evaluate("() => window.app.loadRecentFile(1)")
        pg.wait_for_function("() => window.app.project.layers[0].columns === 4", timeout=10000)
        pg.evaluate("() => window.app.loadRecentFile(1)")   # b is second now
        pg.wait_for_function("() => window.app.project.layers[0].columns === 6", timeout=10000)
        pg.wait_for_timeout(500)
        # saving to a path again replaces its own entry, nothing else
        pg.evaluate("() => window.app.saveProjectToFile()")
        assert sorted(e['path'] for e in _recent(pg)) == sorted([a, b])
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_a_missing_file_is_said_and_never_replaced_by_a_copy(e2e_server, pw_browser, tmp_path):
    context, pg, problems = None, None, []
    gone = str(tmp_path / 'Moved Away.json')
    recent = [{'name': 'Moved Away', 'path': gone, 'timestamp': 1700000000000, 'screenCount': 3}]
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, recent=recent)
        name_before = pg.evaluate("() => window.app.project.name")
        _open_recent_menu(pg, 0)
        pg.wait_for_selector('#recent-missing-modal', timeout=5000)
        text = pg.locator('#recent-missing-modal .recent-missing-text').text_content()
        assert text == ('Moved Away is no longer where it was saved. It may have been moved, '
                        'renamed or deleted. Remove it from Recent Files?'), text
        assert pg.locator('#recent-missing-modal .recent-missing-path').text_content() == gone
        # Keep: the entry stays, the project is untouched
        pg.locator('#recent-missing-modal button', has_text='Keep in list').click()
        pg.wait_for_timeout(200)
        assert pg.locator('#recent-missing-modal').count() == 0
        assert len(_recent(pg)) == 1
        assert pg.evaluate("() => window.app.project.name") == name_before
        # again, Remove: the entry goes
        _open_recent_menu(pg, 0)
        pg.wait_for_selector('#recent-missing-modal', timeout=5000)
        pg.locator('#recent-missing-remove').click()
        pg.wait_for_timeout(200)
        assert _recent(pg) == []
        assert pg.evaluate("() => document.querySelector('#recent-files-list').textContent") == 'No recent files'
        assert pg.evaluate("() => window.app.project.name") == name_before
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_an_entry_without_a_path_opens_its_copy_and_says_so(e2e_server, pw_browser):
    context, pg, problems = None, None, []
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server)
        data = pg.evaluate("async () => { const p = await (await fetch('/api/project')).json();"
                           " p.name = 'Kept Copy'; delete p.is_pristine; return p; }")
        pg.evaluate("(d) => localStorage.setItem('ledRasterRecentFiles', JSON.stringify([{ name: 'Kept Copy',"
                    " timestamp: new Date(2026, 9, 20, 14, 5).getTime(), layerCount: 1, data: d }]))", data)
        assert pg.evaluate("() => window.app.loadRecentFile(0)") is True
        pg.wait_for_function("() => window.app.project.name === 'Kept Copy'", timeout=10000)
        toasts = pg.evaluate("() => [...document.querySelectorAll('#app-toast-host > div')].map(d => d.textContent)")
        assert any(t.startswith('This is the copy of Kept Copy kept in Recent Files from Oct 20, 2026')
                   and t.endswith('not the file itself. Use File > Open to open the file.') for t in toasts), toasts
        # the copy is moved to the top as it was, its date kept
        entry = _recent(pg)[0]
        assert entry['data']['name'] == 'Kept Copy' and not entry.get('path')
        assert problems == [], problems
    finally:
        if context:
            context.close()


# ── a full localStorage never breaks a save or an open ───────────────────

FILL_JS = """() => {
    // to the brim: 1 MB pieces, then halves down to 64 characters
    let n = 0, size = 1024 * 1024;
    while (size >= 64) {
        try { localStorage.setItem('zz_fill_' + n, 'x'.repeat(size)); n++; }
        catch (e) { size = Math.floor(size / 2); }
    }
    try { localStorage.setItem('zz_probe', 'x'.repeat(4096)); return false; }
    catch (e) { return e.name; }
}"""


def test_a_full_local_storage_never_breaks_save_or_open(e2e_server, pw_browser, tmp_path):
    """Matt's Mac log: localStorage full, the Recent update threw inside
    File > Open's success path and the open was logged as failed
    ('The quota has been exceeded.'), the steps after it skipped; on Save
    it was an unhandled rejection after the file was written. Both must
    now finish their whole success path and log no error."""
    context, pg, problems = None, None, []
    saved = str(tmp_path / 'Full Storage.json')
    other = str(tmp_path / 'Opened While Full.json')
    dialogs = Dialogs()
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, dialogs=dialogs)
        pg.evaluate("() => { window.app.project.name = 'Full Storage'; }")
        _set_columns(pg, 30)
        assert pg.evaluate(FILL_JS) == 'QuotaExceededError'
        # Save: the file is written, the status says so, nothing thrown
        dialogs.save_answer = saved
        result = pg.evaluate("() => window.app.saveProjectToFile()")
        assert result['saved'] is True and result['path'] == saved, result
        assert _file_columns(saved) == 30
        assert pg.locator('#status-message').text_content() == 'Project saved to file'
        # File > Open (host dialog) of another show: the whole success path
        _show_file(pg, other, 'Opened While Full', columns=11)
        dialogs.open_answer = other
        _menu(pg, 'open')
        pg.wait_for_function("() => window.app.project.name === 'Opened While Full'", timeout=10000)
        actions = settled(pg, lambda: [e['action'] for e in _client_log(pg)],
                          lambda a: 'load_project_file_success' in a or 'load_project_file_error' in a)
        assert 'load_project_file_success' in actions, ' '.join(actions[-30:])
        pg.wait_for_timeout(500)
        assert _columns(pg) == 11
        assert pg.evaluate("() => window.app._projectOpening") is False
        assert pg.evaluate("() => window.app.history.length") == 1
        log = _client_log(pg)
        bad = [e for e in log if e['action'] in ('load_project_file_error', 'client_unhandled_rejection',
                                                 'client_error')]
        assert bad == [], bad
        # the browser's own chooser (no path) keeps a copy: also no throw
        dialogs.open_answer = None   # unavailable -> the browser's chooser
        with pg.expect_file_chooser() as chooser:
            _menu(pg, 'open')
        chooser.value.set_files(saved)
        pg.wait_for_function("() => window.app.project.name === 'Full Storage'", timeout=10000)
        pg.wait_for_function("() => window.__clog.filter(e => e.action === 'load_project_file_success').length === 2",
                             timeout=10000)
        bad = [e for e in _client_log(pg) if e['action'] in ('load_project_file_error', 'client_unhandled_rejection',
                                                             'client_error')]
        assert bad == [], bad
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_a_full_local_storage_drops_the_oldest_kept_copies(e2e_server, pw_browser):
    """saveRecentFiles never throws: on quota it drops the oldest stored
    copies (path entries cost nothing) and tries again."""
    context, pg, problems = None, None, []
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server)
        out = pg.evaluate("""() => {
            const app = window.app;
            const big = (name) => ({ name, timestamp: Date.now(), screenCount: 1,
                                     data: { name, layers: [], pad: 'y'.repeat(300000) } });
            app.saveRecentFiles([big('Copy 1'), { name: 'On Disk', path: 'C:/shows/On Disk.json',
                timestamp: Date.now(), screenCount: 1 }, big('Copy 2'), big('Copy 3')]);
            // fill what is left
            let n = 0, size = 1024 * 1024;
            while (size >= 64) {
                try { localStorage.setItem('zz_fill_' + n, 'x'.repeat(size)); n++; }
                catch (e) { size = Math.floor(size / 2); }
            }
            let threw = null, ok = null;
            try { ok = app.addToRecentFiles({ name: 'New Copy', layers: [], pad: 'z'.repeat(400000) }); }
            catch (e) { threw = e.name; }
            const names = app.getRecentFiles().map(e => e.name);
            return { threw, ok, names };
        }""")
        assert out['threw'] is None, out
        assert out['ok'] is True, out
        # the newest first; the path entry kept; the oldest copies gone
        assert out['names'][0] == 'New Copy', out
        assert 'On Disk' in out['names'], out
        assert 'Copy 3' not in out['names'], out
        assert problems == [], problems
    finally:
        if context:
            context.close()
