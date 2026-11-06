"""Fixes from the 1.6.0-beta.5 hands-on pass (power and UI).

  - Unsaved edits survive a page reload. The page read "unsaved" off its
    undo history, and a reload starts a new one: the start page's New,
    Open and a Recent file then dropped the edits without asking. The
    answer is kept on the server beside the project (never in it) and
    read back on load; a show a guide's recovery brought back reads
    unsaved across a reload too.
  - A launch over the empty project the start page's X left opens like
    any launch: a startup screen the X takes out again (it kept a
    Screen1). A reload of the same tab is not a launch since 2026-11-04
    (test_reload_keeps_place.py).
  - A distro with multis in use and no output rows: its rows cover every
    multi in use (an older show opens with them filled in, the editor
    shows and builds on them), so + Add output never leaves a multi off
    the face (the owner, 2026-11-03: "You can't have multis without them
    added to the distro").
  - Small ones: a drop that goes through clears an earlier refusal from
    the status bar; Save Screen as Preset offers the name selected; a
    guide puts back the Preferences tab the person had; a distro on a
    service with nothing connected reads as not counted; a cancelled
    project save says Save, not Export; the Pull Sheet's tiles wrap
    instead of running past the window; no en or em dash in the
    displayed strings of the page's code.

Run locally (each session takes its own free port):
    python -m pytest tests/test_reload_unsaved_and_tray_fixes.py -v --browser chromium
"""

import json
import os
import re
import urllib.request

import pytest

from test_start_page_and_recent import (  # noqa: E402
    Dialogs, QUIET, START_PAGE, _open_page, _new_pristine_project, _wait_start,
    _start_up, _set_columns, _show_file, _open_recent_menu, _menu)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(ROOT, 'src', 'static', 'js')

ASK = START_PAGE + "window.__lrdAskUnsaved = true;"


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


def _server_unsaved(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url + '/api/project', timeout=10) as reply:
        return reply.headers.get('X-Project-Unsaved')


def _reload(pg):
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)


def _asked(pg):
    pg.wait_for_selector('#unsaved-changes-modal', state='visible', timeout=5000)


def _cancel(pg):
    pg.locator('#unsaved-changes-modal .app-ask-buttons button', has_text='Cancel').first.click()
    pg.wait_for_function("() => !document.getElementById('unsaved-changes-modal')", timeout=5000)


def _unsaved(pg):
    return pg.evaluate("() => window.app.projectHasUnsavedChanges()")


def _settle_unsaved(pg, url, want):
    """The page's POST of the answer has landed on the server."""
    for _ in range(100):
        if _server_unsaved(url) == want:
            return
        pg.wait_for_timeout(50)
    assert _server_unsaved(url) == want


# ── unsaved edits across a reload ─────────────────────────────────────────

def test_unsaved_edits_survive_a_reload_and_new_open_recent_ask(e2e_server, pw_browser, tmp_path):
    _new_pristine_project(e2e_server)
    show = str(tmp_path / 'Reload Show.json')
    saved = str(tmp_path / 'Reload Saved.json')
    dialogs = Dialogs()
    dialogs.open_answer = show
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=ASK, dialogs=dialogs)
        _wait_start(pg)
        _show_file(pg, show, 'Reload Show', columns=6)
        pg.locator('#start-page-open').click()
        pg.wait_for_function("() => window.app.project.name === 'Reload Show'", timeout=10000)
        pg.wait_for_timeout(500)
        assert _unsaved(pg) is False
        _settle_unsaved(pg, e2e_server, '0')
        _set_columns(pg, 9)
        assert _unsaved(pg) is True
        _settle_unsaved(pg, e2e_server, '1')
        # the reload: the edited show, still unsaved (and no start page
        # over it since 2026-11-04, test_reload_keeps_place.py)
        _reload(pg)
        pg.wait_for_timeout(2500)
        assert not _start_up(pg)
        assert pg.evaluate("() => [window.app.project.name, window.app.project.layers[0].columns]") \
            == ['Reload Show', 9]
        assert _unsaved(pg) is True
        # File > New asks first (the start page's New over a show is File
        # > New); Cancel keeps the edits
        _menu(pg, 'new')
        _asked(pg)
        _cancel(pg)
        assert pg.evaluate("() => window.app.project.layers[0].columns") == 9
        # so do File > Open and a Recent file
        _menu(pg, 'open')
        _asked(pg)
        _cancel(pg)
        assert dialogs.calls.count('open-file') == 1, dialogs.calls
        _open_recent_menu(pg, 0)
        _asked(pg)
        _cancel(pg)
        assert pg.evaluate("() => [window.app.project.name, window.app.project.layers[0].columns]") \
            == ['Reload Show', 9]
        # undo back to the load's own state is still unsaved: the edit
        # was made before the reload
        pg.evaluate("() => window.app.undo()")
        pg.wait_for_timeout(300)
        assert _unsaved(pg) is True
        # a save clears it, and a reload after it reads saved
        dialogs.save_answer = saved
        assert pg.evaluate("() => window.app.saveProjectToFile().then(r => r.saved)") is True
        assert _unsaved(pg) is False
        _settle_unsaved(pg, e2e_server, '0')
        _reload(pg)
        assert _unsaved(pg) is False
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_a_new_project_starts_saved_on_the_server(client):
    """The server's answer: set by the page, read back on the project's
    GET, and a new project starts saved."""
    import routes_project
    routes_project.set_project_unsaved(False)
    assert client.get('/api/project').headers['X-Project-Unsaved'] == '0'
    assert client.post('/api/project/unsaved', json={'unsaved': True}).get_json() == {'unsaved': True}
    assert client.get('/api/project').headers['X-Project-Unsaved'] == '1'
    # nothing about it is in the project itself
    assert 'unsaved' not in json.dumps(sorted(client.get('/api/project').get_json().keys()))
    client.post('/api/project/new')
    assert client.get('/api/project').headers['X-Project-Unsaved'] == '0'
    client.post('/api/project/unsaved', json={'unsaved': True})
    client.post('/api/project/unsaved', json={'unsaved': 'yes'})
    assert client.get('/api/project').headers['X-Project-Unsaved'] == '0'


def test_a_show_a_guide_brought_back_stays_unsaved_across_a_reload(e2e_server, pw_browser):
    """Quit in the middle of a guide: the launch puts the person's show
    back (never saved as it stands, so unsaved), and a reload after that
    still reads unsaved."""
    _new_pristine_project(e2e_server)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(e2e_server + '/api/project', timeout=10) as reply:
        proj = json.loads(reply.read().decode('utf-8'))
    proj.pop('is_pristine', None)
    proj['name'] = 'Guide Show'
    stash = {'project': proj, 'mode': 'pixel-map', 'sheets': [], 'prefs': None, 'tray': None,
             'panels': None, 'layout': None, 'currentLayerId': None, 'at': 0}
    seed = ("try{if(!sessionStorage.getItem('__stash')){sessionStorage.setItem('__stash','1');"
            "localStorage.setItem('lrd_tour_saved_world', " + json.dumps(json.dumps(stash)) + ");}}catch(e){}")
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=ASK + seed)
        _wait_start(pg, 15000)
        assert pg.evaluate("() => window.app.project.name") == 'Guide Show'
        assert _unsaved(pg) is True
        _settle_unsaved(pg, e2e_server, '1')
        _reload(pg)
        _wait_start(pg, 15000)
        assert pg.evaluate("() => window.app.project.name") == 'Guide Show'
        assert _unsaved(pg) is True
        pg.locator('#start-page-new').click()
        _asked(pg)
        _cancel(pg)
        assert problems == [], problems
    finally:
        if context:
            context.close()


# ── a launch over the emptied launch project ──────────────────────────────
# A reload of the same tab keeps the project empty and shows no start page
# (owner, 2026-11-04: tests/test_reload_keeps_place.py). A launch opens a
# new browser tab, and that still opens as every launch does.

def test_a_launch_over_the_emptied_project_opens_like_any_launch(e2e_server, pw_browser):
    _new_pristine_project(e2e_server)
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=START_PAGE)
        _wait_start(pg)
        pg.locator('#start-page-close').click()
        pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
        for _ in range(2):
            pg.close()
            pg = context.new_page()
            pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))
            Dialogs().route(pg)
            pg.goto(e2e_server, wait_until='domcontentloaded')
            pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
            _wait_start(pg)
            # a startup screen under the page, as at launch
            assert pg.evaluate("() => [window.app.project.layers.length,"
                               " window.app._startupTargetId === window.app.project.layers[0].id]") == [1, True]
            pg.locator('#start-page-close').click()
            pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
            srv = pg.evaluate("async () => (await fetch('/api/project')).json()")
            assert srv['layers'] == [] and srv['is_pristine'] is True, srv['layers']
        assert not _start_up(pg)
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_only_the_launch_screen_s_own_delete_keeps_the_project_pristine(client):
    import app as app_module
    app_module.initialize_default_layer()
    first = client.get('/api/project').get_json()['layers'][0]['id']
    # the start page's X: the last screen of the pristine project
    data = client.delete(f'/api/layer/{first}?keep_pristine=1').get_json()
    assert data['layers'] == [] and data['is_pristine'] is True
    # a delete that leaves a screen standing, or carries no marker, ends it
    a = client.post('/api/layer/add', json={'name': 'A', 'columns': 2, 'rows': 2}).get_json()
    client.post('/api/layer/add', json={'name': 'B', 'columns': 2, 'rows': 2})
    data = client.delete(f"/api/layer/{a['id']}?keep_pristine=1").get_json()
    assert len(data['layers']) == 1 and data['is_pristine'] is False


# ── distro faces cover the multis in use ──────────────────────────────────

FACE_SHOW_JS = """async () => {
    const j = (method, url, body) => fetch(url, { method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body) }).then(r => r.json());
    await window.app._layerSavesSettled();
    await fetch('/api/project/new', { method: 'POST' });
    const made = await j('POST', '/api/layer/add', {
        name: 'Wall', columns: 16, rows: 4, cabinet_width: 200, cabinet_height: 200,
        offset_x: 0, offset_y: 0 });
    const p = await j('GET', '/api/project');
    const l = p.layers.find(x => x.id === made.id);
    Object.assign(l, {
        powerFlowPattern: 'tl-v', lastPowerFlowPattern: 'tl-v', powerOrganized: true,
        powerVoltage: 208, powerAmperage: 20, panelWatts: 400, powerBreakoutType: 'soca-true1',
        powerSplitters: { enabled: false, maxWays: 3, manual: { merge: [], split: [] } },
        powerSocaDistro: { 1: 'd1', 2: 'd1' },
    });
    // saved before output rows existed: the boxes and their types only
    p.distros = [{ id: 'd1', name: 'VX', ratingA: 400, voltage: 208, phase: 3,
                   boxTypes: { 1: 'soca208', 2: 'soca208' } }];
    p.name = 'Face Show';
    p.app_version = '1.4.0';
    return p;
}"""


def _open_face_show(pg):
    project = pg.evaluate(FACE_SHOW_JS)
    with pg.expect_file_chooser() as chooser:
        pg.evaluate("() => window.app.loadProjectFromFile()")
    chooser.value.set_files({'name': 'face-show.json', 'mimeType': 'application/json',
                             'buffer': json.dumps(project).encode('utf-8')})
    pg.wait_for_function("() => window.app.project.name === 'Face Show'"
                         " && document.getElementById('status-message').textContent.includes('Project loaded')",
                         timeout=15000)
    pg.wait_for_timeout(600)


ROWS_JS = """() => (window.app.getDistros()[0].outputRows || null)"""
FACE_WARN_JS = """() => [...document.querySelectorAll('#hardware-dock *')]
    .filter(e => e.children.length === 0 && /not on .* face/.test(e.textContent))
    .map(e => e.textContent)"""


def _row_summary(rows):
    return [(r['connector'], r['count'], r['coupling']) for r in (rows or [])]


def test_an_older_show_opens_with_rows_for_every_multi_in_use(e2e_server, pw_browser):
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=QUIET)
        _open_face_show(pg)
        assert sorted(pg.evaluate("() => [...window.app._distroMultiNumbers('d1').keys()]")) == [1, 2]
        assert _row_summary(pg.evaluate(ROWS_JS)) == [('soca', 2, 'll')]
        srv = pg.evaluate("async () => (await (await fetch('/api/project')).json()).distros")
        assert _row_summary(srv[0].get('outputRows')) == [('soca', 2, 'll')], srv
        # the open's own state: no undo step brings the empty face back
        assert pg.evaluate("() => window.app.history.length") == 1
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_add_output_builds_on_the_multis_in_use(e2e_server, pw_browser):
    """A distro with multis in use and no rows (plugged by demand): the
    editor shows the rows that cover them and + Add output adds on top -
    it made a face of one output, and the second multi read "not on VX's
    face"."""
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=QUIET)
        _open_face_show(pg)
        pg.locator('.view-tab[data-mode="power"]').click()
        pg.wait_for_function("() => window.canvasRenderer.viewMode === 'power'")
        pg.evaluate("() => { delete window.app.getDistros()[0].outputRows;"
                    " window.app._circuitTailCache = null; window.app.renderHardwareDock(); }")
        pg.locator('[data-hwdock="distro-d1"] .hw-dock-gear').first.click()
        pg.wait_for_selector('[data-lrd-field="distro-row-count-d1-r1"]', state='visible')
        assert pg.locator('[data-lrd-field="distro-row-count-d1-r1"]').input_value() == '2'
        pg.locator('[data-lrd-field="distro-row-add-d1"]').click()
        pg.wait_for_timeout(500)
        assert _row_summary(pg.evaluate(ROWS_JS)) == [('soca', 2, 'll'), ('soca', 1, 'll')]
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(300)
        assert pg.evaluate(FACE_WARN_JS) == []
        assert problems == [], problems
    finally:
        if context:
            context.close()


# ── the small ones ────────────────────────────────────────────────────────

def test_a_drop_that_goes_through_clears_an_earlier_refusal(e2e_server, pw_browser):
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=QUIET)
        # the socket's own word lands first
        pg.wait_for_function("() => document.getElementById('status-message').textContent === 'Connected'",
                             timeout=10000)
        pg.evaluate("() => window.app._dockSay('Screen1 runs at 208V, and a Multi 120 output feeds screens up to 120V')")
        assert 'Multi 120' in pg.locator('#status-message').text_content()
        pg.evaluate("() => window.app._dockPerformDrop({ type: 'nothing' }, { kind: 'none' })")
        assert pg.locator('#status-message').text_content() == 'Ready'
        # a sentence that is not the dock's own is left alone
        pg.evaluate("() => { window.app._dockSay('refused');"
                    " document.getElementById('status-message').textContent = 'Project saved to file';"
                    " window.app._dockPerformDrop({ type: 'nothing' }, { kind: 'none' }); }")
        assert pg.locator('#status-message').text_content() == 'Project saved to file'
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_save_screen_as_preset_offers_the_name_selected(e2e_server, pw_browser):
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=QUIET)
        pg.locator('#btn-save-preset').click()
        pg.wait_for_selector('#preset-save-name', state='visible')
        pg.wait_for_function("() => document.activeElement && document.activeElement.id === 'preset-save-name'")
        pg.keyboard.type('Pillar')
        assert pg.locator('#preset-save-name').input_value() == 'Pillar'
        pg.locator('#preset-save-cancel').click()
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_a_guide_puts_back_the_preferences_tab_the_person_had(e2e_server, pw_browser):
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=QUIET)
        pg.locator('#btn-preferences').click()
        pg.locator('#preferences-modal .pm-tabstrip .view-tab[data-key="data"]').click()
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(300)
        pg.evaluate("() => { window.QuickStart.start(); }")
        pg.wait_for_function("() => window.QuickStart.state().visible", timeout=15000)
        # a guide's step opens another tab
        pg.evaluate("() => window.app.showPreferencesTab('stock')")
        pg.evaluate("() => window.QuickStart.end()")
        pg.wait_for_function("() => !window.QuickStart.state().visible", timeout=15000)
        pg.wait_for_timeout(500)
        pg.locator('#btn-preferences').click()
        active = pg.evaluate("() => document.querySelector('#preferences-modal .pm-tabstrip .view-tab.active').dataset.key")
        assert active == 'data'
        pg.keyboard.press('Escape')
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_a_distro_with_nothing_connected_reads_as_not_counted(e2e_server, pw_browser):
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=QUIET)
        _open_face_show(pg)
        pg.locator('.view-tab[data-mode="power"]').click()
        pg.evaluate("""() => { const a = window.app;
            a.addDistro({ name: 'SPARE' });
            const s = a.addService ? a.addService() : null;
            const sid = s && s.id;
            a.getDistros().forEach(d => { d.serviceId = sid; });
            a._circuitTailCache = null; a.renderHardwareDock(); }""")
        chips = pg.evaluate("""() => [...document.querySelectorAll('.hw-dock-svc-chip')]
            .map(c => [c.textContent, c.classList.contains('hw-dock-svc-chip-idle')])""")
        assert ['VX 400 A', False] in chips, chips
        assert ['SPARE 400 A · nothing connected', True] in chips, chips
        sums = pg.evaluate("() => [...document.querySelectorAll('.hw-dock-svc-sum')].map(s => s.textContent)")
        assert any(s.startswith('ratings 400 A') for s in sums), sums
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_a_cancelled_project_save_says_save(e2e_server, pw_browser):
    dialogs = Dialogs()
    dialogs.save_answer = {'ok': False, 'cancelled': True, 'unavailable': False}
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=QUIET, dialogs=dialogs)
        pg.evaluate("() => window.app.saveProjectToFile()")
        pg.wait_for_function("() => [...document.querySelectorAll('#app-toast-host > div')]"
                             ".some(t => t.textContent.includes('canceled'))", timeout=5000)
        texts = pg.evaluate("() => [...document.querySelectorAll('#app-toast-host > div')].map(t => t.textContent)")
        assert any('Save canceled, nothing was saved.' in t for t in texts), texts
        assert not any('Export canceled' in t for t in texts), texts
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_the_pull_sheet_tiles_wrap_inside_the_window(e2e_server, pw_browser):
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=QUIET)
        board = pg.evaluate("""() => { const host = document.createElement('div');
            host.className = 'pull-sheet-board'; host.style.width = '1534px';
            host.innerHTML = '<div class="pull-pos" style="width:560px;height:20px"></div>'
                + '<div class="pull-pos" style="width:560px;height:20px"></div>'
                + '<div class="pull-pos pull-totals" style="width:440px;height:20px"></div>';
            document.body.appendChild(host);
            const out = [host.scrollWidth, host.clientWidth, getComputedStyle(host).flexWrap];
            host.remove(); return out; }""")
        assert board[2] == 'wrap', board
        assert board[0] <= board[1], board
        assert problems == [], problems
    finally:
        if context:
            context.close()


# The page's code shows no en or em dash: in a string it would be on
# screen (a range reads "1-6", an empty cell is blank). Comments may say
# what they like; a regex that matches a dash the user typed is not text.
_DASH = re.compile('[–—]')


def _code_without_comments(src):
    out, i, n, quote = [], 0, len(src), None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if src.startswith('//', i):
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if src.startswith('/*', i):
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch in '\'"`':
            quote = ch
        out.append(ch)
        i += 1
    return ''.join(out)


def test_no_en_or_em_dash_in_the_page_s_strings():
    bad = []
    for name in sorted(os.listdir(JS_DIR)):
        if not name.endswith('.js') or name.endswith('.min.js'):
            continue
        with open(os.path.join(JS_DIR, name), encoding='utf-8') as fh:
            code = _code_without_comments(fh.read())
        for k, line in enumerate(code.splitlines(), 1):
            if not _DASH.search(line):
                continue
            # a pattern that reads a dash someone typed
            if re.search(r'\[[^\]]*[–—][^\]]*\]', line):
                continue
            bad.append(f'{name}: {line.strip()[:120]}')
    assert not bad, '\n'.join([''] + bad)
