"""The app shell, Recent, the start page, exports and the dialogs (1.6.0
QA round 3).

Each test is one finding from the third hand test, held to its fix:

  - Export clicked straight after typing a new Rev exported nothing: the
    Rev's commit added a REVISIONS row, the dialog grew, and the button
    moved out from under the mouse between down and up. The press now
    commits the field first and the click lands (helpers.js
    commitEditOnPress).
  - Opening a show from Recent (and File > Open, and New) dropped unsaved
    changes without asking. All three ask first in the app's own dialog:
    Save, Don't Save, Cancel (app-project-io confirmUnsavedChanges).
  - A launch after quitting in the middle of a guide put the project back
    and showed no start page. The start page shows on every launch
    (app-presets maybeOpenStartupPicker).
  - With browser storage full, Save listed nothing in Recent and said
    nothing. The oldest entries make room, and when even that fails the
    person is told (app-logs-recent saveRecentFiles).
  - Esc did not close the File or Help menu or the panel picker
    (app-menubar _escapeClosesDialog).
  - No native alert(), confirm() or prompt() is left in the app's own JS:
    every question is the app's dialog (app-dialogs.js).
  - Ctrl+J with several screens selected copied only one.
  - Cosmetic: the Data tray's processor picker at 800 px, the Recent
    submenu's grey, the pull sheet copy's "Tell me and I'll extend it.",
    the binder's mixed type sizes and "+2 more" box names, "ports 1-1",
    and twenty Cat6 runs labelled "1R … 1 (20)".

Run locally (each session takes its own free port):
    python -m pytest tests/test_round3_ui_fixes.py -v --browser chromium
"""

import io
import json
import os
import re
import urllib.request

import pytest

from test_start_page_and_recent import (  # noqa: E402
    Dialogs, QUIET, START_PAGE, _open_page, _new_pristine_project, _wait_start,
    _start_up, _set_columns, _show_file, _open_recent_menu, _menu)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_DIR = os.path.join(ROOT, 'src', 'static', 'js')
INDEX_HTML = os.path.join(ROOT, 'src', 'templates', 'index.html')

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


ASK_UNSAVED = QUIET + "window.__lrdAskUnsaved = true;"


def _shown(pg, sel):
    return pg.evaluate("(s) => { const m = document.querySelector(s);"
                       " return !!m && getComputedStyle(m).display !== 'none'; }", sel)


# ── 1. Export right after a Rev edit ──────────────────────────────────────

def test_export_clicked_right_after_a_rev_edit_exports(e2e_server, pw_browser):
    _new_pristine_project(e2e_server)
    dialogs = Dialogs()
    dialogs.save_answer = {'ok': False, 'cancelled': True}
    context, pg, problems = _open_page(pw_browser, e2e_server, dialogs=dialogs)
    try:
        posts = []

        def fake_pdf(route):
            posts.append(route.request.url)
            route.fulfill(status=200, content_type='application/pdf', body=b'%PDF-1.4\n%%EOF\n')
        pg.route('**/api/export/pdf-from-pages', fake_pdf)
        pg.click('#btn-export')
        pg.wait_for_timeout(400)
        pg.select_option('#export-format', 'binder')
        pg.evaluate("() => { window.app.setBinderField('revisions', [], 'Clear'); window.app._renderBinderRevisionRows(); }")
        for n, rev in enumerate(['R2', 'R3', 'R4'], start=1):
            if not _shown(pg, '#export-modal'):
                pg.click('#btn-export')
                pg.wait_for_timeout(400)
            pg.click('#export-binder-rev', click_count=3)
            pg.keyboard.type(rev)
            button = pg.locator('#export-confirm')
            button.scroll_into_view_if_needed()
            box = button.bounding_box()
            # a real press: down and up where the button was when it began
            pg.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            for _ in range(60):
                if len(posts) >= n:
                    break
                pg.wait_for_timeout(250)
            assert len(posts) == n, f'Export after typing Rev {rev} exported nothing'
            assert pg.evaluate("() => window.app.getPullSheetSettings().rev") == rev
            pg.wait_for_function("() => document.getElementById('export-modal').style.display === 'none'")
        revs = pg.evaluate("() => window.app.getBinderInfo().revisions.map(r => r.rev)")
        assert revs == ['R2', 'R3', 'R4'], revs
        assert problems == [], problems
    finally:
        context.close()


# ── 2. Unsaved changes are asked about ───────────────────────────────────

def _unsaved_dialog(pg):
    pg.wait_for_selector('#unsaved-changes-modal', state='visible', timeout=5000)
    return pg.evaluate("""() => {
        const m = document.getElementById('unsaved-changes-modal');
        return { title: m.querySelector('.app-ask-title').textContent,
                 text: m.querySelector('.app-ask-text').textContent,
                 buttons: [...m.querySelectorAll('.app-ask-buttons button')].map(b => b.textContent) };
    }""")


def _press(pg, label):
    pg.locator('#unsaved-changes-modal .app-ask-buttons button', has_text=label).first.click()
    pg.wait_for_function("() => !document.getElementById('unsaved-changes-modal')", timeout=5000)


def test_recent_open_and_new_ask_before_unsaved_changes_go(e2e_server, pw_browser, tmp_path):
    _new_pristine_project(e2e_server)
    show = str(tmp_path / 'Other Show.json')
    saved = str(tmp_path / 'Mine.json')
    dialogs = Dialogs()
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=ASK_UNSAVED, dialogs=dialogs)
        _show_file(pg, show, 'Other Show', columns=6)
        pg.evaluate("(p) => window.app.addToRecentFiles({ name: 'Other Show', layers: [{}] }, { path: p })", show)
        # nothing changed yet: the pristine project opens the recent show unasked
        _set_columns(pg, 12)
        assert pg.evaluate("() => window.app.projectHasUnsavedChanges()") is True
        # Recent: asked, Save / Don't Save / Cancel; Cancel keeps everything
        _open_recent_menu(pg, 0)
        ask = _unsaved_dialog(pg)
        assert ask['title'] == 'Save changes?'
        assert ask['buttons'] == ['Save', "Don't Save", 'Cancel'], ask
        assert "If you don't save, your changes are lost." in ask['text'], ask
        _press(pg, 'Cancel')
        assert pg.evaluate("() => [window.app.project.name, window.app.project.layers[0].columns]") == ['Untitled Project', 12]
        # New (the toolbar) and File > Open ask the same; Esc is Cancel
        pg.click('#btn-new')
        assert _unsaved_dialog(pg)['buttons'] == ['Save', "Don't Save", 'Cancel']
        pg.keyboard.press('Escape')
        pg.wait_for_function("() => !document.getElementById('unsaved-changes-modal')")
        _menu(pg, 'open')
        _unsaved_dialog(pg)
        _press(pg, 'Cancel')
        assert dialogs.calls.count('open-file') == 0, 'Cancel must not go on to the Open dialog'
        assert pg.evaluate("() => window.app.project.layers[0].columns") == 12
        # Save writes the file first, then the recent show opens
        dialogs.save_answer = saved
        _open_recent_menu(pg, 0)
        _unsaved_dialog(pg)
        _press(pg, 'Save')
        pg.wait_for_function("() => window.app.project.name === 'Other Show'"
                             " && document.getElementById('status-message').textContent.includes('Project loaded')",
                             timeout=10000)
        pg.wait_for_timeout(500)
        with open(saved, encoding='utf-8') as fh:
            assert json.load(fh)['layers'][0]['columns'] == 12
        # opened as saved: nothing to ask; an edit, then Don't Save opens unsaved
        assert pg.evaluate("() => window.app.projectHasUnsavedChanges()") is False
        _set_columns(pg, 9)
        # not awaited: the question has to be answered first
        pg.evaluate("() => { window.app.loadRecentFile(1); }")   # Mine.json, listed by the Save
        _unsaved_dialog(pg)
        _press(pg, "Don't Save")
        pg.wait_for_function("() => window.app.project.layers[0].columns === 12", timeout=10000)
        with open(show, encoding='utf-8') as fh:
            assert json.load(fh)['layers'][0]['columns'] == 6, "Don't Save wrote the show"
        # undo back to the saved state reads as saved again
        _set_columns(pg, 5)
        pg.evaluate("() => window.app.undo()")
        pg.wait_for_timeout(600)
        assert pg.evaluate("() => window.app.projectHasUnsavedChanges()") is False
        assert problems == [], problems
    finally:
        if context:
            context.close()


# ── 3. The start page on every launch ────────────────────────────────────

def test_a_launch_after_quitting_mid_guide_shows_the_start_page(e2e_server, pw_browser):
    """The guide's stash (quickstart.js) holds the person's own show, not
    the pristine startup project: the launch puts it back AND shows the
    start page; X keeps the show."""
    _new_pristine_project(e2e_server)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(e2e_server + '/api/project', timeout=10) as reply:
        proj = json.loads(reply.read().decode('utf-8'))
    proj.pop('is_pristine', None)
    proj['name'] = 'My Show'
    stash = {'project': proj, 'mode': 'pixel-map', 'sheets': [], 'prefs': None, 'tray': None,
             'panels': None, 'layout': None, 'currentLayerId': None, 'at': 0}
    seed = ("try{if(!sessionStorage.getItem('__stash')){sessionStorage.setItem('__stash','1');"
            "localStorage.setItem('lrd_tour_saved_world', " + json.dumps(json.dumps(stash)) + ");}}catch(e){}")
    context = None
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server, init=START_PAGE + seed)
        _wait_start(pg, 15000)
        assert pg.evaluate("() => window.app.project.name") == 'My Show'
        assert pg.evaluate("() => localStorage.getItem('lrd_tour_saved_world')") is None
        pg.locator('#start-page-close').click()
        pg.wait_for_timeout(500)
        assert not _start_up(pg)
        assert pg.evaluate("() => [window.app.project.name, window.app.project.layers.length]") == ['My Show', 1]
        assert problems == [], problems
    finally:
        if context:
            context.close()


# ── 4. Recent Files with browser storage full ────────────────────────────

FILL_JS = """() => {
    let n = window.__fill || 0;
    for (const size of [262144, 65536, 8192, 1024, 128, 16, 1]) {
        const chunk = 'z'.repeat(size);
        for (;;) { try { localStorage.setItem('qa_fill_' + (n++), chunk); } catch (e) { break; } }
    }
    window.__fill = n;
    return n;
}"""

UNFILL_JS = """() => { Object.keys(localStorage).filter(k => k.startsWith('qa_fill_'))
    .forEach(k => localStorage.removeItem(k)); }"""

TOASTS_JS = """() => { const h = document.getElementById('app-toast-host');
    return h ? [...h.children].map(t => t.textContent) : []; }"""


def test_recent_files_with_storage_full_makes_room_or_says_so(e2e_server, pw_browser):
    recent = [{'name': f'Show {i}', 'path': f'C:/Shows/Show {i}.json', 'timestamp': 1000 - i,
               'screenCount': 1} for i in range(1, 4)]
    context, pg, problems = _open_page(pw_browser, e2e_server, recent=recent)
    try:
        pg.evaluate(FILL_JS)
        ok = pg.evaluate("() => window.app.addToRecentFiles({ name: 'New Show', layers: [] },"
                         " { path: 'C:/Shows/New Show.json' })")
        listed = pg.evaluate("() => window.app.getRecentFiles().map(f => f.name)")
        assert ok is True and listed[0] == 'New Show', listed
        assert 'Show 1' in listed, 'the newest of the old entries stays'
        assert pg.evaluate(TOASTS_JS) == []
        # nothing left to drop: the list is gone and storage still full
        pg.evaluate("() => localStorage.removeItem('ledRasterRecentFiles')")
        pg.evaluate(FILL_JS)
        ok = pg.evaluate("() => window.app.addToRecentFiles({ name: 'Another Show', layers: [] },"
                         " { path: 'C:/Shows/Another Show.json' })")
        assert ok is False
        toasts = pg.evaluate(TOASTS_JS)
        assert any('Recent Files could not be updated' in t and 'full' in t for t in toasts), toasts
    finally:
        pg.evaluate(UNFILL_JS)
        context.close()


# ── 5. Esc closes the menus and the panel picker ─────────────────────────

def test_escape_closes_the_file_and_help_menus_and_the_panel_picker(e2e_server, pw_browser):
    _new_pristine_project(e2e_server)
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        for menu in ('file', 'help'):
            pg.locator(f'#menu-bar .menu-item[data-menu="{menu}"]').click()
            pg.wait_for_timeout(150)
            assert _shown(pg, f'#menu-{menu}')
            pg.keyboard.press('Escape')
            pg.wait_for_timeout(150)
            assert not _shown(pg, f'#menu-{menu}'), f'{menu} menu still open after Esc'
        # Add Screen's picker: Esc is Cancel, nothing added
        n = pg.evaluate("() => window.app.project.layers.length")
        pg.evaluate("() => window.app.openPresetPicker({ mode: 'add' })")
        pg.wait_for_function("() => document.getElementById('preset-picker-modal').style.display === 'block'")
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(300)
        assert not _shown(pg, '#preset-picker-modal')
        assert pg.evaluate("() => window.app.project.layers.length") == n
        assert problems == [], problems
    finally:
        context.close()


def test_escape_in_the_picker_from_the_start_page_goes_back_to_it(e2e_server, pw_browser):
    _new_pristine_project(e2e_server)
    context, pg, problems = _open_page(pw_browser, e2e_server, init=START_PAGE)
    try:
        _wait_start(pg)
        pg.locator('#start-page-new').click()
        pg.wait_for_function("() => document.getElementById('preset-picker-modal').style.display === 'block'")
        pg.keyboard.press('Escape')
        _wait_start(pg, 5000)
        assert not _shown(pg, '#preset-picker-modal')
        assert pg.evaluate("() => window.app.project.layers.length") == 1
        assert problems == [], problems
    finally:
        context.close()


# ── 6. No native alert / confirm / prompt ────────────────────────────────

NATIVE = re.compile(r'(?<![\w.$])(?:window\s*\.\s*)?(alert|confirm|prompt)\s*\(')
VENDORED = {'socket.io.min.js'}


def _code(text):
    """`text` without its comments (block and line)."""
    text = re.sub(r'/\*.*?\*/', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), text, flags=re.S)
    return '\n'.join(re.sub(r'(^|[^:])//.*$', r'\1', line) for line in text.split('\n'))


def test_no_native_alert_confirm_or_prompt_in_the_app():
    found = []
    for name in sorted(os.listdir(JS_DIR)):
        if not name.endswith('.js') or name in VENDORED:
            continue
        with open(os.path.join(JS_DIR, name), encoding='utf-8') as fh:
            for no, line in enumerate(_code(fh.read()).split('\n'), start=1):
                if NATIVE.search(line):
                    found.append(f'{name}:{no}: {line.strip()}')
    with open(INDEX_HTML, encoding='utf-8') as fh:
        html = re.sub(r'<!--.*?-->', '', fh.read(), flags=re.S)
    for no, line in enumerate(_code(html).split('\n'), start=1):
        if NATIVE.search(line):
            found.append(f'index.html:{no}: {line.strip()}')
    assert found == [], 'native dialogs left (use the app\'s own, app-dialogs.js):\n' + '\n'.join(found)


def test_the_app_dialog_answers_ok_cancel_esc_and_a_typed_name(e2e_server, pw_browser):
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        pg.evaluate("() => { window.__a = window.app.appConfirm('Go?', { id: 'qa-ask' }); }")
        pg.wait_for_selector('#qa-ask')
        pg.locator('#qa-ask .btn-primary').click()
        assert pg.evaluate("() => window.__a") is True
        pg.evaluate("() => { window.__a = window.app.appConfirm('Go?', { id: 'qa-ask' }); }")
        pg.wait_for_selector('#qa-ask')
        pg.keyboard.press('Escape')
        assert pg.evaluate("() => window.__a") is False
        pg.evaluate("() => { window.__a = window.app.appPrompt('Name?', 'Old', { id: 'qa-ask' }); }")
        pg.wait_for_selector('#qa-ask')
        assert pg.locator('#qa-ask .app-ask-input').input_value() == 'Old'
        pg.locator('#qa-ask .app-ask-input').fill('New Name')
        pg.keyboard.press('Enter')
        assert pg.evaluate("() => window.__a") == 'New Name'
        # two questions at once: the second waits for the first
        pg.evaluate("""() => { window.__b = [];
            window.app.appConfirm('One', { id: 'qa-one' }).then(v => window.__b.push(['one', v]));
            window.app.appConfirm('Two', { id: 'qa-two' }).then(v => window.__b.push(['two', v])); }""")
        pg.wait_for_selector('#qa-one')
        assert pg.locator('.app-ask-modal').count() == 1
        pg.locator('#qa-one .btn-primary').click()
        pg.wait_for_selector('#qa-two')
        pg.keyboard.press('Escape')
        pg.wait_for_function("() => window.__b.length === 2")
        assert pg.evaluate("() => window.__b") == [['one', True], ['two', False]]
        assert problems == [], problems
    finally:
        context.close()


def test_reset_defaults_asks_in_the_app_dialog(e2e_server, pw_browser):
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        pg.click('#btn-preferences')
        pg.wait_for_timeout(300)
        pg.click('#preferences-reset')
        pg.wait_for_selector('#preferences-reset-modal', state='visible', timeout=3000)
        assert pg.locator('#preferences-reset-modal .app-ask-text').text_content() == \
            'Put every preference back to its default?'
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(200)
        assert _shown(pg, '#preferences-modal'), 'Esc on the question keeps Preferences open'
        pg.click('#preferences-cancel')
        assert problems == [], problems   # no native dialog
    finally:
        context.close()


# ── 7. Ctrl+J duplicates every selected screen ───────────────────────────

def test_ctrl_j_duplicates_every_selected_screen(e2e_server, pw_browser):
    _new_pristine_project(e2e_server)
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        pg.evaluate("() => window.app.handleMenuAction('duplicate')")
        pg.wait_for_function("() => window.app.project.layers.length === 2")
        ids = pg.evaluate("() => window.app.project.layers.map(l => l.id)")
        pg.evaluate("(ids) => window.app.setSelectedLayersByIds(ids, ids[1])", ids)
        pg.locator('#main-canvas').hover()
        pg.keyboard.press('Control+j')
        pg.wait_for_function("() => window.app.project.layers.length === 4", timeout=10000)
        pg.wait_for_timeout(400)
        names = pg.evaluate("() => window.app.project.layers.map(l => l.name)")
        assert names == ['Screen1', 'Screen2', 'Screen3', 'Screen4'], names
        made = pg.evaluate("() => window.app.project.layers.slice(2).map(l => l.id)")
        assert sorted(pg.evaluate("() => [...window.app.selectedLayerIds]")) == sorted(made)
        # Edit > Duplicate does the same with the copies selected
        pg.evaluate("() => window.app.handleMenuAction('duplicate')")
        pg.wait_for_function("() => window.app.project.layers.length === 6", timeout=10000)
        names = pg.evaluate("() => window.app.project.layers.map(l => l.name)")
        assert len(set(names)) == 6, names
        assert problems == [], problems
    finally:
        context.close()


# ── 8. Cosmetic ───────────────────────────────────────────────────────────

def test_the_processor_picker_is_whole_at_800_px(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 800, 'height': 768})
    context.add_init_script(QUIET)
    pg = context.new_page()
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
        pg.locator('[data-mode="data-flow"]').click()
        pg.wait_for_timeout(600)
        fit = pg.evaluate("""() => {
            const s = document.getElementById('processor-add-device');
            const text = s.options[s.selectedIndex] ? s.options[s.selectedIndex].text : '';
            const ctx = document.createElement('canvas').getContext('2d');
            const cs = getComputedStyle(s);
            ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
            // The select draws its own arrow (appearance: none) inside its
            // right padding, so the text's room is the client box less the
            // padding the stylesheet actually gives it, read here rather
            // than guessed: a flat allowance failed on the Linux runner's
            // wider font while the text sat whole on screen.
            const pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
            return { text, need: ctx.measureText(text).width, pad,
                     have: s.clientWidth, appearance: cs.appearance };
        }""")
        assert fit['text'] == 'Add a processor…', fit
        assert fit['appearance'] == 'none', fit
        # the arrow lives in the right padding: the text plus both paddings
        assert fit['pad'] >= 16, fit
        assert fit['need'] + fit['pad'] <= fit['have'], fit
    finally:
        context.close()


def _luminance(rgb):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def test_the_recent_submenu_detail_is_readable(e2e_server, pw_browser):
    recent = [{'name': 'Show A', 'path': 'C:/Shows/Show A.json', 'timestamp': 1, 'screenCount': 3}]
    context, pg, problems = _open_page(pw_browser, e2e_server, recent=recent)
    try:
        pg.locator('#menu-bar .menu-item[data-menu="file"]').click()
        pg.locator('#menu-file .menu-option[data-action="recent-files"]').hover()
        pg.wait_for_timeout(250)
        got = pg.evaluate("""() => {
            const d = document.querySelector('#recent-files-list .recent-file-date');
            let el = d, bg = 'rgba(0, 0, 0, 0)';
            while (el && /rgba\\(0, 0, 0, 0\\)|transparent/.test(bg)) { bg = getComputedStyle(el).backgroundColor; el = el.parentElement; }
            return { fg: getComputedStyle(d).color, bg };
        }""")
        rgb = lambda s: tuple(int(x) for x in re.findall(r'\d+', s)[:3])
        hi, lo = sorted([_luminance(rgb(got['fg'])), _luminance(rgb(got['bg']))], reverse=True)
        ratio = (hi + 0.05) / (lo + 0.05)
        assert ratio >= 4.5, (got, ratio)
    finally:
        context.close()


def test_the_pull_sheet_copy_drops_the_templates_note_to_its_author():
    import openpyxl
    import pull_sheet
    data, _ = pull_sheet.build_workbook({'positions': []}, {})
    wb = openpyxl.load_workbook(io.BytesIO(data))
    texts = [c.value for ws in wb for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    assert not [t for t in texts if "Tell me" in t or "I'll extend" in t], 'app wording only'
    assert any(t.startswith('If not 0, a position sits past the scanned columns') for t in texts)


def test_binder_cells_keep_one_type_size_and_box_names_never_fold(e2e_server, pw_browser):
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        out = pg.evaluate("""() => {
            const app = window.app;
            const book = { measureCtx: document.createElement('canvas').getContext('2d') };
            const fits = (t, w) => { book.measureCtx.font = app._bFont(24, 400);
                                     return book.measureCtx.measureText(t).width <= w + 0.5; };
            // a card's BACKUP cell whose first member is a hair too wide
            const first = 'CVT4K-S E-F backs up CVT10 A';
            book.measureCtx.font = app._bFont(24, 400);
            const w = book.measureCtx.measureText(first).width * 0.92;
            const backup = app._bCellLines(book, first + ', CVT10 B; CVT4K-S G-H backs up CVT4K-S C-D',
                                           24, 400, w, 4, false);
            // a loop box's name in its column (words, never folded)
            const box = app._bCellLines(book, 'CVT4K-S E-F · loop of CVT10 A 1-8, CVT10 B 1-8 on sockets 9-16',
                                        24, 400, 180, 2, true);
            return { backup, backupFits: backup.every(t => fits(t, w)), box,
                     boxFits: box.every(t => fits(t, 180)) };
        }""")
        assert out['backupFits'], out
        assert out['boxFits'] and not any('more' in t for t in out['box']), out
        assert problems == [], problems
    finally:
        context.close()
    with open(os.path.join(JS_DIR, 'app-binder.js'), encoding='utf-8') as fh:
        src = fh.read()
    assert "{ title: 'breakout box', w: 1.3, list: 2, words: true }" in src


def test_one_socket_reads_port_1_and_returns_fold(e2e_server, pw_browser):
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        assert pg.evaluate("() => window.app._dockPortSpanText([1])") == 'port 1'
        assert pg.evaluate("() => window.app._dockPortSpanText([9, 10, 11, 12, 13, 14])") == 'ports 9-14'
        names = [x for n in range(1, 11) for x in (str(n), f'{n}R')]
        assert pg.evaluate("(n) => window.app._pullCompressNames(n)", names) == '1-10, 1R-10R'
        assert pg.evaluate("(n) => window.app._pullCompressNames(n)", ['1R', '1']) == '1R, 1'
        assert pg.evaluate("(n) => window.app._pullCompressNames(n)", ['3R', '1R', '2R', '7R']) == '1R-3R, 7R'
        assert problems == [], problems
    finally:
        context.close()
