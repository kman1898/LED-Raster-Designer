"""The app shell, the Screens list, start-up and the dialogs (1.6.0 QA pass).

Each test here is one finding from the beta.4 hand test, held to the fix:

  - A multi-canvas show opens on the canvas it was saved on. Selecting a
    screen activates its canvas, and the open used to select layers[0]
    before the server held the show: a PUT /api/canvas/<id>/active for a
    canvas only the incoming show has (404), the show on the wrong canvas,
    and that wrong canvas saved back (app-canvas-ui _selectOpeningScreen).
  - Duplicate, paste and Add Screen never make a second screen of a name
    already in use (app-screen-groups _nextDuplicateName, routes_layers
    _next_free_screen_name).
  - Esc closes the right-click menu and the Preferences, Export, About,
    Shortcuts, Logs and What's New dialogs, as their Cancel / Close
    (app-menubar _escapeClosesDialog).
  - User text says Screen, not Layer; the pull sheet preferences carry no
    em dash placeholders.
  - The header wraps instead of running under the Screens panel at 1024
    and 800 px, and the 1600 px layout is untouched.
  - The Processing select shows "NovaStar COEX A10s/A8s (1G)" whole.
  - The panel picker opens on the whole library, not the last search.
  - Help > Check for Updates answers in the app's own message, not alert().
  - The "Lock Selected" words toggle the lock.
  - With no screen (the start-up picker cancelled), Screen Info is blank
    and takes no typing.

Run locally (each session takes its own free port):
    python -m pytest tests/test_shell_qa_fixes.py -v --browser chromium
"""

import copy
import json
import os
import re
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, 'src', 'templates', 'index.html')

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


NO_GUIDE = "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
WITH_PICKER = NO_GUIDE + "window.__lrdStartupPicker = true;"


def _post(url, path, body=b''):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url + path, data=body, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=10) as reply:
        return json.loads(reply.read().decode('utf-8'))


def _get(url, path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url + path, timeout=10) as reply:
        return json.loads(reply.read().decode('utf-8'))


def _open_page(pw_browser, url, init=NO_GUIDE, width=1600, height=950):
    context = pw_browser.new_context(viewport={'width': width, 'height': height})
    context.add_init_script(init)
    pg = context.new_page()
    # Page errors, failed API answers and native dialogs. The panel
    # library's update check at launch is refused on purpose (conftest
    # points it at a dead port), so that answer is not ours.
    problems = []
    pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))
    pg.on('response', lambda r: problems.append(f'{r.status} {r.request.method} {r.url}')
          if '/api/' in r.url and r.status >= 400
          and '/api/panel-catalog/refresh' not in r.url else None)
    pg.on('dialog', lambda d: (problems.append(f'native {d.type}: {d.message}'), d.dismiss()))
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.wait_for_timeout(600)
    return context, pg, problems


def _fresh_project(url):
    """The server's New project: one Screen1, on canvas c1."""
    made = _post(url, '/api/project/new')
    assert [l['name'] for l in made['layers']] == ['Screen1'], made['layers']
    return made


def _names(pg):
    return pg.evaluate("() => window.app.project.layers.map(l => l.name)")


# ── A multi-canvas show opens on its saved canvas ─────────────────────────

def _two_canvas_show(url):
    """A show whose FIRST screen sits on a canvas other than the saved
    active one, and whose canvas ids the server's current project does not
    have: the shape of the show the testers opened."""
    base = _fresh_project(url)
    show = copy.deepcopy(base)
    show.pop('is_pristine', None)
    show['name'] = 'Two Canvas Show'
    c = show['canvases'][0]
    first = dict(c, id='c7', name='Upstage')
    second = dict(c, id='c8', name='Downstage', workspace_x=2200)
    show['canvases'] = [first, second]
    a = show['layers'][0]
    a['canvas_id'] = 'c7'
    a['name'] = 'Upstage Wall'
    b = copy.deepcopy(a)
    b['id'] = a['id'] + 1
    b['canvas_id'] = 'c8'
    b['name'] = 'Downstage Wall'
    show['layers'] = [a, b]
    show['active_canvas_id'] = 'c8'
    return show


STATE_JS = """() => ({
    active: window.app.project.active_canvas_id,
    current: window.app.currentLayer ? window.app.currentLayer.name : null,
})"""


def test_a_multi_canvas_show_opens_on_its_saved_canvas(e2e_server, pw_browser, tmp_path):
    show = _two_canvas_show(e2e_server)
    path = tmp_path / 'two_canvas_show.json'
    path.write_text(json.dumps(show), encoding='utf-8')
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        with pg.expect_file_chooser() as chooser:
            pg.evaluate("() => window.app.loadProjectFromFile()")
        chooser.value.set_files(str(path))
        pg.wait_for_function("() => window.app.project.name === 'Two Canvas Show'"
                             " && !window.app._projectOpening", timeout=10000)
        pg.wait_for_timeout(1200)
        assert pg.evaluate(STATE_JS) == {'active': 'c8', 'current': 'Downstage Wall'}
        assert _get(e2e_server, '/api/project')['active_canvas_id'] == 'c8'
        # a reload stays on it too
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
        pg.wait_for_timeout(1200)
        assert pg.evaluate(STATE_JS) == {'active': 'c8', 'current': 'Downstage Wall'}
        assert _get(e2e_server, '/api/project')['active_canvas_id'] == 'c8'
        assert problems == [], problems
    finally:
        context.close()


def test_a_multi_canvas_recent_file_opens_on_its_saved_canvas(e2e_server, pw_browser):
    show = _two_canvas_show(e2e_server)
    show['name'] = 'Two Canvas Recent'
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        pg.evaluate("""(show) => {
            localStorage.setItem('ledRasterRecentFiles', JSON.stringify([{
                name: show.name, timestamp: Date.now(), layerCount: show.layers.length, data: show
            }]));
            window.app.loadRecentFile(0);
        }""", show)
        pg.wait_for_function("() => window.app.project.name === 'Two Canvas Recent'"
                             " && !window.app._projectOpening", timeout=10000)
        pg.wait_for_timeout(1200)
        assert pg.evaluate(STATE_JS) == {'active': 'c8', 'current': 'Downstage Wall'}
        assert _get(e2e_server, '/api/project')['active_canvas_id'] == 'c8'
        assert problems == [], problems
    finally:
        pg.evaluate("() => localStorage.removeItem('ledRasterRecentFiles')")
        context.close()


# ── Names stay unique ─────────────────────────────────────────────────────

def test_duplicate_paste_and_add_screen_never_repeat_a_name(e2e_server, pw_browser):
    _fresh_project(e2e_server)
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        assert _names(pg) == ['Screen1']
        dup = "() => window.app.handleMenuAction('duplicate')"
        pick = "(name) => window.app.selectLayer(window.app.project.layers.find(l => l.name === name))"
        pg.evaluate(dup)
        pg.wait_for_function("() => window.app.project.layers.length === 2")
        assert _names(pg) == ['Screen1', 'Screen2']
        # Screen1 again, beside a Screen2: Screen3, not a second Screen2
        pg.evaluate(pick, 'Screen1')
        pg.locator('#main-canvas').hover()
        pg.keyboard.press('Control+j')
        pg.wait_for_function("() => window.app.project.layers.length === 3")
        assert _names(pg) == ['Screen1', 'Screen2', 'Screen3']
        # copy / paste Screen1: Screen4
        pg.evaluate(pick, 'Screen1')
        pg.evaluate("() => { window.app.copyLayer(); window.app.pasteLayer(); }")
        pg.wait_for_function("() => window.app.project.layers.length === 4")
        assert _names(pg)[-1] == 'Screen4'
        # Add Screen after a delete: four screens, Screen4 taken, so Screen5
        pg.evaluate(pick, 'Screen2')
        pg.evaluate("() => window.app.deleteLayer(window.app.currentLayer.id)")
        pg.wait_for_function("() => window.app.project.layers.length === 3")
        added = pg.evaluate("""async () => (await fetch('/api/layer/add', {method: 'POST',
            headers: {'Content-Type': 'application/json'}, body: '{}'})).json()""")
        assert added['name'] == 'Screen5', added['name']
        # the increment the group copy shares, case-blind
        assert pg.evaluate("() => window.app._nextDuplicateName('Wall2', ['Wall2', 'wall3'])") == 'Wall4'
        assert pg.evaluate("() => window.app._nextDuplicateName('Main', ['Main', 'Main 1'])") == 'Main 2'
        assert problems == [], problems
    finally:
        context.close()


# ── Esc closes the menu and the dialogs ───────────────────────────────────

def _shown(pg, el_id):
    return pg.evaluate("(id) => { const m = document.getElementById(id);"
                       " return !!m && getComputedStyle(m).display !== 'none'; }", el_id)


SCREEN_POINT_JS = """() => {
    const r = window.canvasRenderer, l = window.app.project.layers[0];
    const box = r.canvas.getBoundingClientRect();
    return [box.left + r.panX + (l.offset_x + l.cabinet_width * 1.5) * r.zoom,
            box.top + r.panY + (l.offset_y + l.cabinet_height * 1.5) * r.zoom];
}"""


def test_escape_closes_the_right_click_menu_and_only_that(e2e_server, pw_browser):
    _fresh_project(e2e_server)
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        x, y = pg.evaluate(SCREEN_POINT_JS)
        pg.mouse.click(x, y, button='right')
        pg.wait_for_timeout(300)
        assert _shown(pg, 'context-menu')
        # the right-click picked the cabinet under it (Pixel Map)
        assert pg.evaluate("() => window.app.pixelMapSelection.size") == 1
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(200)
        assert not _shown(pg, 'context-menu')
        assert pg.evaluate("() => window.app.pixelMapSelection.size") == 1
        # the next Esc reaches the cabinet selection as before
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(200)
        assert pg.evaluate("() => window.app.pixelMapSelection.size") == 0
        # the menu's own words say Screen
        pg.mouse.click(x, y, button='right')
        pg.wait_for_timeout(300)
        labels = pg.evaluate("() => [...document.querySelectorAll('#context-menu .menu-option')]"
                             ".filter(e => e.offsetParent).map(e => e.textContent)")
        assert any(t.startswith('Delete Screen') for t in labels), labels
        assert not [t for t in labels if 'Layer' in t], labels
        pg.keyboard.press('Escape')
        assert problems == [], problems
    finally:
        context.close()


DIALOGS = [
    ('preferences-modal', "() => document.getElementById('btn-preferences').click()"),
    ('export-modal', "() => document.getElementById('btn-export').click()"),
    ('about-modal', "() => window.app.handleMenuAction('about')"),
    ('shortcuts-modal', "() => window.app.handleMenuAction('keyboard-shortcuts')"),
    ('logs-modal', "() => window.app.handleMenuAction('show-logs')"),
    ('whatsnew-modal', "() => window.app.handleMenuAction('whats-new')"),
]


def test_escape_closes_each_dialog_as_cancel(e2e_server, pw_browser):
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        for modal_id, opener in DIALOGS:
            pg.evaluate(opener)
            pg.wait_for_function("(id) => { const m = document.getElementById(id);"
                                 " return !!m && getComputedStyle(m).display !== 'none'; }",
                                 arg=modal_id, timeout=5000)
            pg.keyboard.press('Escape')
            pg.wait_for_timeout(250)
            assert not _shown(pg, modal_id), f'{modal_id} still open after Esc'
        # Preferences: Esc is Cancel, never Save
        pg.evaluate(DIALOGS[0][1])
        pg.wait_for_timeout(300)
        field = '#' + pg.evaluate("""() => [...document.querySelectorAll('#preferences-modal input')]
            .find(e => ['text', 'number'].includes(e.type) && e.offsetParent && !e.disabled && e.id).id""")
        was = pg.locator(field).input_value()
        pg.locator(field).fill('77')
        pg.locator(field).press('Tab')
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(250)
        assert not _shown(pg, 'preferences-modal')
        pg.evaluate(DIALOGS[0][1])
        pg.wait_for_timeout(300)
        assert pg.locator(field).input_value() == was
        pg.keyboard.press('Escape')
        assert problems == [], problems
    finally:
        context.close()


def test_escape_leaves_a_dialog_under_a_colors_window(e2e_server, pw_browser):
    """Something floating over the dialog owns the Esc: a Colors window
    open over Preferences closes, Preferences stays."""
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        pg.evaluate(DIALOGS[0][1])
        pg.wait_for_timeout(300)
        pg.evaluate("""() => { const w = document.createElement('div');
            w.className = 'lrd-cw-window'; w.id = 'qa-fake-colors';
            w.style.cssText = 'position:fixed;left:0;top:0;width:40px;height:40px;';
            document.body.appendChild(w); }""")
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(250)
        assert _shown(pg, 'preferences-modal')
        pg.evaluate("() => document.getElementById('qa-fake-colors').remove()")
        pg.keyboard.press('Escape')
        pg.wait_for_timeout(250)
        assert not _shown(pg, 'preferences-modal')
        assert problems == [], problems
    finally:
        context.close()


# ── Words: Screen, not Layer; no em dash placeholders ─────────────────────

def _visible_html():
    with open(INDEX_HTML, encoding='utf-8') as f:
        html = f.read()
    blank = lambda m: re.sub(r'[^\n]', ' ', m.group(0))
    for pat in (r'<!--.*?-->', r'<script.*?</script>', r'<style.*?</style>'):
        html = re.sub(pat, blank, html, flags=re.S)
    return html


def test_user_text_says_screen_not_layer():
    html = _visible_html()
    # what a person reads: element text and the attributes shown to them
    shown = re.findall(r'>([^<>]+)<', html)
    shown += re.findall(r'\b(?:title|data-tooltip|data-label|placeholder)="([^"]*)"', html)
    offenders = [s.strip() for s in shown if re.search(r'\blayers?\b', s, re.I)
                 # the PSD format's own word for what the file holds
                 and not re.search(r'PSD|Layered|One layer per screen|separate layers'
                                   r'|group of layers|Layers with nothing', s)]
    assert offenders == [], offenders


def test_pull_sheet_preferences_have_no_em_dash_placeholders():
    html = _visible_html()
    assert '—' not in html, [l.strip() for l in html.splitlines() if '—' in l]


def test_recent_files_count_screens(e2e_server, pw_browser):
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        dates = pg.evaluate("""() => {
            const p = window.app.project;
            localStorage.setItem('ledRasterRecentFiles', JSON.stringify([
                {name: 'One', timestamp: Date.now(), screenCount: 1, layerCount: 1, data: p},
                {name: 'Two', timestamp: Date.now(), screenCount: 2, layerCount: 2, data: p}]));
            window.app.updateRecentFilesMenu();
            return [...document.querySelectorAll('.recent-file-date')].map(e => e.textContent);
        }""")
        assert [d.split('·')[-1].strip() for d in dates] == ['1 screen', '2 screens'], dates
    finally:
        pg.evaluate("() => localStorage.removeItem('ledRasterRecentFiles')")
        context.close()


# ── Narrow windows ────────────────────────────────────────────────────────

HEADER_JS = """() => {
    const box = (el) => el.getBoundingClientRect();
    const bar = document.getElementById('toolbar');
    const strip = document.getElementById('canvas-controls');
    const tb = box(bar), cs = box(strip);
    const out = (el, frame) => { const r = box(el); return r.width > 0 && (r.right > frame.right + 0.5 || r.bottom > frame.bottom + 0.5); };
    return {
        height: Math.round(tb.height),
        title: getComputedStyle(document.querySelector('#toolbar .lrd-app-title')).display,
        toolbarOut: [...bar.querySelectorAll('button, input, h1')].filter(e => out(e, tb)).map(e => e.id || e.tagName),
        stripOut: [...strip.querySelectorAll('button, input, label')].filter(e => out(e, cs)).map(e => e.id || e.className),
    };
}"""


@pytest.mark.parametrize('width', [1024, 800])
def test_the_header_wraps_in_a_narrow_window(e2e_server, pw_browser, width):
    context, pg, problems = _open_page(pw_browser, e2e_server, width=width, height=900)
    try:
        st = pg.evaluate(HEADER_JS)
        assert st['toolbarOut'] == [] and st['stripOut'] == [], st
        assert st['title'] == 'none', st
    finally:
        context.close()


def test_the_header_is_unchanged_at_1600(e2e_server, pw_browser):
    context, pg, problems = _open_page(pw_browser, e2e_server, width=1600, height=950)
    try:
        st = pg.evaluate(HEADER_JS)
        assert st == {'height': 50, 'title': 'inline', 'toolbarOut': [], 'stripOut': []}, st
        assert pg.evaluate("() => getComputedStyle(document.getElementById('canvas-controls')).flexWrap") == 'nowrap'
    finally:
        context.close()


# ── The Processing select shows the whole name ────────────────────────────

def test_the_processing_select_shows_the_whole_coex_1g_name(e2e_server, pw_browser):
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        pg.locator('[data-mode="data-flow"]').click()
        pg.wait_for_timeout(400)
        # The name shown closed (the value set without a change event, so
        # the screen keeps its processor). It either fits its one line or,
        # where the font is wider than the room (Linux's DejaVu Sans), wraps
        # word by word onto as many lines as the box is tall: every word
        # fits the room, and the box holds every line.
        fit = pg.evaluate("""() => {
            const s = document.getElementById('processor-type');
            const was = s.value;
            const opt = [...s.options].find(o => o.value === 'novastar-coex-1g');
            s.value = opt.value;
            const cs = getComputedStyle(s);
            const ctx = document.createElement('canvas').getContext('2d');
            ctx.font = cs.font;
            const room = s.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
            const inner = s.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
            const w = t => ctx.measureText(t).width;
            let lines = 1, line = '';
            for (const word of opt.text.split(' ')) {
                const next = line ? line + ' ' + word : word;
                if (line && w(next) > room) { lines += 1; line = word; } else line = next;
            }
            const out = {text: opt.text, need: w(opt.text), room, lines,
                         widest: Math.max(...opt.text.split(' ').map(w)),
                         wraps: cs.whiteSpace === 'normal', inner,
                         lineHeight: parseFloat(cs.fontSize) * 1.15};
            s.value = was;
            return out;
        }""")
        assert fit['text'] == 'NovaStar COEX A10s/A8s (1G)', fit
        if fit['need'] > fit['room']:
            assert fit['wraps'] and fit['widest'] <= fit['room'], fit
            assert fit['inner'] >= fit['lines'] * fit['lineHeight'] - 1, fit
    finally:
        context.close()


# ── The panel picker, the update check, the lock words, no screen ─────────

def test_the_panel_picker_opens_on_the_whole_library(e2e_server, pw_browser):
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        pg.evaluate("() => window.app.openPresetPicker()")
        pg.wait_for_function("() => (window.app._panelCatalogFlat || []).length > 0", timeout=10000)
        pg.locator('#panel-catalog-search').fill('ROE')
        pg.evaluate("() => { const s = document.getElementById('panel-catalog-mfr');"
                    " s.value = s.options[1].value; s.dispatchEvent(new Event('change')); }")
        pg.locator('#preset-picker-cancel').click()
        pg.evaluate("() => window.app.openPresetPicker()")
        pg.wait_for_timeout(500)
        assert pg.locator('#panel-catalog-search').input_value() == ''
        assert pg.locator('#panel-catalog-mfr').input_value() == ''
        pg.locator('#preset-picker-cancel').click()
        assert problems == [], problems
    finally:
        context.close()


def test_check_for_updates_answers_in_the_app(e2e_server, pw_browser):
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        pg.route('**/api/update/check**', lambda r: r.fulfill(
            status=200, content_type='application/json',
            body='{"available": false, "current_version": "9.9.9"}'))
        pg.locator('#menu-bar .menu-item[data-menu="help"]').click()
        pg.locator('#menu-help .menu-option[data-action="check-updates"]').click()
        pg.wait_for_function("() => { const h = document.getElementById('app-toast-host');"
                             " return !!h && h.textContent.includes('9.9.9'); }", timeout=5000)
        assert 'You are running the latest version (9.9.9).' in pg.evaluate(
            "() => document.getElementById('app-toast-host').textContent")
        assert problems == [], problems   # no native alert
    finally:
        context.close()


def test_the_lock_selected_words_toggle_the_lock(e2e_server, pw_browser):
    _fresh_project(e2e_server)
    context, pg, problems = _open_page(pw_browser, e2e_server)
    try:
        locked = "() => !!window.app.currentLayer.locked"
        assert pg.evaluate(locked) is False
        pg.locator('#toggle-lock-selected-label').click()
        pg.wait_for_timeout(400)
        assert pg.evaluate(locked) is True
        pg.get_by_text('Lock Selected', exact=True).click()
        pg.wait_for_timeout(400)
        assert pg.evaluate(locked) is False
        assert problems == [], problems
    finally:
        context.close()


SCREEN_INFO_JS = """() => [...document.querySelector(
        '#left-sidebar .tab-panel[data-tab="pixel-map"]').querySelectorAll('.panel-content input')]
    .filter(e => ['text', 'number'].includes(e.type) && e.offsetParent)
    .map(e => ({id: e.id, value: e.value, disabled: e.disabled}))"""


def test_screen_info_with_no_screen_is_blank_and_takes_no_typing(e2e_server, pw_browser):
    _fresh_project(e2e_server)
    context, pg, problems = _open_page(pw_browser, e2e_server, init=WITH_PICKER)
    try:
        pg.wait_for_function("() => document.getElementById('preset-picker-modal').style.display === 'block'"
                             " && window.app._pickerMode === 'startup'", timeout=10000)
        pg.locator('#preset-picker-cancel').click()
        pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
        pg.wait_for_timeout(500)
        fields = pg.evaluate(SCREEN_INFO_JS)
        assert fields and not [f for f in fields if not f['disabled'] or f['value'] != ''], [f for f in fields if not f['disabled'] or f['value'] != '']
        # Add Screen brings the fields back, filled
        pg.evaluate("() => window.app.openPresetPicker()")
        pg.wait_for_function("() => (window.app._panelCatalogFlat || []).length > 0", timeout=10000)
        pg.locator('#panel-catalog-list .panel-catalog-row').first.click()
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("() => window.app.project.layers.length === 1", timeout=10000)
        pg.wait_for_timeout(600)
        fields = pg.evaluate(SCREEN_INFO_JS)
        assert fields and not [f for f in fields if f['disabled']], fields
        assert pg.locator('#screen-columns').input_value() != ''
        assert problems == [], problems
    finally:
        context.close()
