"""A new project starts by picking its panel (1.6.0).

Owner, 2026-11-02: "remove the preferences option where we set the
resolution size of the panel. And instead, on start-up, we open up the
panel library and choose a panel from the dropdown. The name of the tile
that we use in each screen should be the name of the tile that is chosen
by default. Then if we want to change it, we can."

  - Preferences has no Panel size (px), Panel size (mm) or Panel weight
    rows; the kg / lb choice is its own Weight unit row. A record saved
    with the old keys is harmless: getPreferences drops them.
  - A launch (always a fresh, pristine project) and File > New open the
    Add Screen modal in its startup mode, "Choose a panel"
    (app-presets.js maybeOpenStartupPicker). Opening a saved show never
    does. It never opens over another dialog (_launchUiBusy).
  - A pick replaces the startup screen with a Screen1 of that panel: its
    pixels, millimeters, weight, watts and the saved panel model, the name
    in Screen Info's Panel field. Cancel leaves the project empty, and Add
    Screen works from there.
  - Add Screen with nothing picked copies the last screen's panel and says
    so; with no screen to copy, it waits for a pick.

Automated browsers never see the startup picker (navigator.webdriver, the
rule the guide and the What's New window keep), so every other module
boots to its familiar Screen1. This module turns it on with
window.__lrdStartupPicker = true before the page loads.

Run locally (each session takes its own free port):
    python -m pytest tests/test_startup_panel_picker.py -v --browser chromium
"""

import json
import os
import re
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and its preferences) the way this
    module found them."""


ENABLE_PICKER = (
    "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
    "window.__lrdStartupPicker = true;"
)

MODAL_JS = """() => {
    const modal = document.getElementById('preset-picker-modal');
    const btn = document.getElementById('preset-picker-add');
    return {
        shown: modal.style.display === 'block',
        mode: window.app._pickerMode || null,
        title: document.getElementById('preset-picker-title').textContent,
        brief: document.getElementById('preset-picker-subtitle').textContent,
        confirm: btn.textContent,
        disabled: btn.disabled,
        summary: document.getElementById('preset-picker-summary').textContent,
        defaultRow: (() => {
            const r = document.querySelector('#preset-picker-list .preset-picker-row[data-kind="default"]');
            return r ? r.textContent : null;
        })(),
    };
}"""

LAYER_JS = """(id) => {
    const l = id == null ? window.app.project.layers[window.app.project.layers.length - 1]
        : window.app.project.layers.find(x => x.id === id);
    if (!l) return null;
    return {
        id: l.id, name: l.name, columns: l.columns, rows: l.rows,
        cabinet_width: l.cabinet_width, cabinet_height: l.cabinet_height,
        panel_width_mm: l.panel_width_mm, panel_height_mm: l.panel_height_mm,
        panel_weight: l.panel_weight, weight_unit: l.weight_unit, panelWatts: l.panelWatts,
        panelModelId: l.panelModelId ?? null, panelModelName: l.panelModelName ?? null,
        panelModelHalves: l.panelModelHalves ?? null,
    };
}"""

# A library panel carrying every figure a pick writes, typed into the
# search box and clicked in the list, the user's way.
PICK_PANEL_JS = """async (avoidPx) => {
    const app = window.app;
    for (let i = 0; i < 200 && !(app._panelCatalogFlat && app._panelCatalogFlat.length); i++) {
        await new Promise(r => setTimeout(r, 50));
    }
    const p = app._panelCatalogFlat.find(x => x.pixels_w && x.pixels_h && x.width_mm && x.height_mm
        && x.weight_kg != null && x.watts_max != null && !avoidPx.includes(x.pixels_w) && x.name);
    const search = document.getElementById('panel-catalog-search');
    search.value = p.name;
    search.dispatchEvent(new Event('input', {bubbles: true}));
    let row = null;
    for (let i = 0; i < 100 && !row; i++) {
        await new Promise(r => setTimeout(r, 50));
        row = [...document.querySelectorAll('#panel-catalog-list .panel-catalog-row')]
            .find(el => el.dataset.mfr === p._mfr && el.dataset.name === p.name) || null;
    }
    row.click();
    return {mfr: p._mfr, name: p.name, label: app._catalogModelLabel(p._mfr, p),
            pixels_w: p.pixels_w, pixels_h: p.pixels_h,
            width_mm: p.width_mm, height_mm: p.height_mm,
            weight_kg: p.weight_kg, watts_max: p.watts_max};
}"""


def _server_project(pg):
    return pg.evaluate("async () => (await fetch('/api/project')).json()")


def _new_pristine_project(url):
    """What a launch finds: the server's fresh project (New), one startup
    screen, pristine. Straight to loopback, no proxy lookup (conftest's
    e2e_server probe does the same)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url + '/api/project/new', data=b'', method='POST')
    with opener.open(req, timeout=10) as reply:
        assert reply.status == 200
        assert json.loads(reply.read().decode('utf-8'))['is_pristine'] is True


def _open_page(pw_browser, url, init=ENABLE_PICKER):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(init)
    pg = context.new_page()
    # Errors on the page and failed API answers. The panel library's
    # update check at launch is refused on purpose (conftest points it at a
    # dead port), so that answer, and the browser's console line for a
    # failed fetch, which the response check already covers, are not ours.
    problems = []
    pg.on('pageerror', lambda e: problems.append('pageerror: ' + str(e)))
    pg.on('console', lambda m: problems.append('console: ' + m.text)
          if m.type == 'error' and not m.text.startswith('Failed to load resource') else None)
    pg.on('response', lambda r: problems.append(f'{r.status} {r.url}')
          if '/api/' in r.url and r.status >= 400
          and '/api/panel-catalog/refresh' not in r.url else None)
    pg.goto(url, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    return context, pg, problems


def _wait_picker(pg, timeout=10000):
    pg.wait_for_function(
        "() => document.getElementById('preset-picker-modal').style.display === 'block'"
        " && window.app._pickerMode === 'startup'", timeout=timeout)
    return pg.evaluate(MODAL_JS)


def _picker_shown(pg):
    return pg.evaluate("() => document.getElementById('preset-picker-modal').style.display === 'block'")


def _expect_panel(layer, panel):
    assert layer['cabinet_width'] == panel['pixels_w'], (layer, panel)
    assert layer['cabinet_height'] == panel['pixels_h'], (layer, panel)
    assert layer['panel_width_mm'] == panel['width_mm'], (layer, panel)
    assert layer['panel_height_mm'] == panel['height_mm'], (layer, panel)
    assert layer['weight_unit'] == 'kg' and layer['panel_weight'] == panel['weight_kg'], (layer, panel)
    assert layer['panelWatts'] == panel['watts_max'], (layer, panel)
    assert layer['panelModelId'] == f"{panel['mfr']}|{panel['name']}", layer
    assert layer['panelModelName'] == panel['label'], layer


# ── Preferences ───────────────────────────────────────────────────────────

def test_the_panel_preference_rows_are_gone():
    with open(os.path.join(ROOT, 'src', 'templates', 'index.html'), encoding='utf-8') as fh:
        html = fh.read()
    for gone in ('pref-panel-width', 'pref-panel-height', 'pref-panel-width-mm',
                 'pref-panel-height-mm', 'pref-panel-weight',
                 'Panel size (px)', 'Panel size (mm)', 'Panel weight'):
        assert gone not in html, gone
    # the weight unit is its own row
    row = re.search(r'<label>Weight unit</label>\s*<div class="prefs-row">\s*'
                    r'<select id="pref-weight-unit"', html)
    assert row, 'no Weight unit row holding #pref-weight-unit'
    with open(os.path.join(ROOT, 'src', 'static', 'js', 'app-preferences.js'), encoding='utf-8') as fh:
        prefs_js = fh.read()
    for key in ('panelWidth:', 'panelHeight:', 'panelWidthMM:', 'panelHeightMM:', 'panelWeight:'):
        assert key not in prefs_js, key


def test_old_saved_panel_preferences_are_harmless(e2e_server, pw_browser):
    """A record saved before 1.6.0 still carries the panel keys: nothing
    reads them, the dialog opens and saves without them, and a screen
    made in an empty project takes the server's cabinet, not theirs."""
    context, pg, problems = _open_page(pw_browser, e2e_server,
                                       init="try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    try:
        before = pg.evaluate("async () => (await fetch('/api/preferences')).json()")
        old = dict(before or {}, panelWidth=999, panelHeight=777, panelWidthMM=1234,
                   panelHeightMM=4321, panelWeight=88, weightUnit='kg')
        pg.evaluate("""async (p) => {
            await fetch('/api/preferences', {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify(p)});
            window.app._serverPreferences = p;
        }""", old)
        prefs = pg.evaluate("() => window.app.getPreferences()")
        for key in ('panelWidth', 'panelHeight', 'panelWidthMM', 'panelHeightMM', 'panelWeight'):
            assert key not in prefs, key
        # Preferences opens and saves; the saved record drops the old keys
        pg.evaluate("() => window.app.openPreferencesModal()")
        pg.wait_for_timeout(300)
        pg.locator('#preferences-save').click()
        pg.wait_for_timeout(600)
        saved = pg.evaluate("async () => (await fetch('/api/preferences')).json()")
        assert not {'panelWidth', 'panelHeight', 'panelWeight'} & set(saved), saved
        # an empty project's first screen: the server's cabinet
        pg.evaluate("""async () => {
            const proj = await (await fetch('/api/project')).json();
            proj.layers = []; proj.groups = [];
            const back = await (await fetch('/api/project', {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify(proj)})).json();
            window.app.project = back; window.app.currentLayer = null;
            window.app.selectedLayerIds = new Set();
            window.app.updateUI();
        }""")
        pg.evaluate("() => window.app.addLayer()")
        pg.wait_for_function("() => window.app.project.layers.length === 1", timeout=5000)
        made = pg.evaluate(LAYER_JS, None)
        assert (made['cabinet_width'], made['cabinet_height']) == (128, 128), made
        assert made['panel_weight'] == 20, made
        assert problems == [], problems
    finally:
        pg.evaluate("""async (p) => { await fetch('/api/preferences', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(p || {})}); }""", before)
        context.close()


# ── the startup picker ────────────────────────────────────────────────────

def test_launch_opens_the_picker_and_a_pick_makes_screen1_of_that_panel(e2e_server, pw_browser):
    context, pg, problems = None, None, []
    try:
        _new_pristine_project(e2e_server)
        context, pg, problems = _open_page(pw_browser, e2e_server)
        st = _wait_picker(pg)
        assert st['title'] == 'Choose a panel', st
        assert st['brief'] == ("Pick the panel for this project's first screen, from your presets "
                               "or the panel catalog. Cancel starts with no screens."), st
        assert st['confirm'] == 'Use Panel', st
        # nothing to copy at a start: no "nothing selected" row, the button waits
        assert st['defaultRow'] is None and st['disabled'] is True, st
        assert st['summary'] == 'Nothing selected. Pick a panel or a preset.', st
        startup_id = pg.evaluate("() => window.app.project.layers[0].id")
        panel = pg.evaluate(PICK_PANEL_JS, [128])
        assert pg.evaluate(MODAL_JS)['disabled'] is False
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("(id) => window.app.project.layers.length === 1"
                             " && window.app.project.layers[0].id !== id"
                             " && window.app.project.layers[0].panelModelName", arg=startup_id, timeout=10000)
        pg.wait_for_timeout(600)
        assert not _picker_shown(pg)
        made = pg.evaluate(LAYER_JS, None)
        assert made['name'] == 'Screen1', made
        _expect_panel(made, panel)
        # the server holds the same screen, and only it
        srv = _server_project(pg)
        assert [l['id'] for l in srv['layers']] == [made['id']], srv['layers']
        srv_layer = srv['layers'][0]
        for k in ('cabinet_width', 'cabinet_height', 'panel_width_mm', 'panel_height_mm',
                  'panel_weight', 'panelWatts', 'panelModelId', 'panelModelName'):
            assert srv_layer[k] == made[k], (k, srv_layer[k], made[k])
        assert srv['is_pristine'] is False
        # Screen Info's Panel field shows the picked panel's name
        assert pg.evaluate("() => document.getElementById('panel-model-name').value") == panel['label']
        # the history starts from the picked screen: nothing to undo
        assert pg.evaluate("() => window.app.history.length") == 1
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_nothing_picked_add_screen_copies_the_last_screens_panel(e2e_server, pw_browser):
    context, pg, problems = None, None, []
    try:
        _new_pristine_project(e2e_server)
        context, pg, problems = _open_page(pw_browser, e2e_server)
        _wait_picker(pg)
        panel = pg.evaluate(PICK_PANEL_JS, [128])
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("() => window.app.project.layers.length === 1"
                             " && window.app.project.layers[0].panelModelName", timeout=10000)
        pg.wait_for_timeout(600)
        first = pg.evaluate(LAYER_JS, None)
        # Add Screen, nothing picked
        pg.evaluate("() => window.app.openPresetPicker()")
        pg.wait_for_selector('#preset-picker-list .preset-picker-row[data-kind="default"]', timeout=5000)
        st = pg.evaluate(MODAL_JS)
        assert st['mode'] == 'add' and st['title'] == 'Add Screen', st
        assert st['defaultRow'].startswith('Same as Screen1'), st
        assert st['summary'] == f"Nothing selected, will use Screen1's panel ({panel['label']}).", st
        assert st['disabled'] is False, st
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("() => window.app.project.layers.length === 2", timeout=10000)
        pg.wait_for_timeout(800)
        second = pg.evaluate(LAYER_JS, None)
        assert second['name'] == 'Screen2', second
        for k in ('cabinet_width', 'cabinet_height', 'panel_width_mm', 'panel_height_mm',
                  'panel_weight', 'weight_unit', 'panelWatts',
                  'panelModelId', 'panelModelName', 'panelModelHalves'):
            assert second[k] == first[k], (k, first[k], second[k])
        assert pg.evaluate("() => document.getElementById('panel-model-name').value") == panel['label']
        srv = next(l for l in _server_project(pg)['layers'] if l['id'] == second['id'])
        assert (srv['panelModelName'], srv['panelWatts']) == (first['panelModelName'], first['panelWatts']), srv
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_a_preset_with_a_panel_names_it_on_the_new_screen(e2e_server, pw_browser):
    """A preset saved from a screen that carries a panel hands the panel's
    name to the screen it makes, so Screen Info's Panel field shows it."""
    context, pg, problems = None, None, []
    name = 'Startup Picker Test Preset'
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server,
                                           init="try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
        pg.evaluate("""async (name) => {
            const app = window.app;
            const l = app.project.layers.find(x => (x.type || 'screen') === 'screen');
            const data = app.serializeLayerAsPreset({ ...l, panelModelId: null,
                panelModelName: 'House Tile 500', panelModelHalves: null });
            await app.savePresetToServer(name, data);
        }""", name)
        n = pg.evaluate("() => window.app.project.layers.length")
        pg.evaluate("() => window.app.openPresetPicker()")
        row = f'#preset-picker-list .preset-picker-row[data-key="{name}"]'
        pg.wait_for_selector(row, timeout=5000)
        pg.locator(row).click()
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("(n) => window.app.project.layers.length === n + 1", arg=n, timeout=10000)
        pg.wait_for_timeout(800)
        made = pg.evaluate(LAYER_JS, None)
        assert made['panelModelName'] == 'House Tile 500', made
        assert pg.evaluate("() => document.getElementById('panel-model-name').value") == 'House Tile 500'
        pg.evaluate("(id) => window.app.deleteLayer(id)", made['id'])
        pg.wait_for_timeout(600)
        assert problems == [], problems
    finally:
        if pg:
            pg.evaluate("(name) => window.app.deletePresetOnServer(name)", name)
        if context:
            context.close()


def test_file_new_opens_the_picker_and_cancel_leaves_an_empty_project(e2e_server, pw_browser):
    context, pg, problems = None, None, []
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server)
        # the boot project here is not a fresh one (the session's Screen1
        # was added by hand): no picker
        pg.wait_for_timeout(1500)
        assert not _picker_shown(pg)
        pg.evaluate("() => window.app.handleMenuAction('new')")
        st = _wait_picker(pg)
        assert st['title'] == 'Choose a panel' and st['disabled'] is True, st
        pg.locator('#preset-picker-cancel').click()
        pg.wait_for_function("() => window.app.project.layers.length === 0", timeout=10000)
        pg.wait_for_timeout(600)
        assert not _picker_shown(pg)
        assert _server_project(pg)['layers'] == []
        assert pg.evaluate("() => window.app.currentLayer") is None
        assert pg.evaluate("() => window.app.history.length") == 1
        # an empty project works: every view draws, the panels fill
        for mode in ('cabinet-id', 'data-flow', 'power', 'show-look', 'pixel-map'):
            pg.locator(f'[data-mode="{mode}"]').click()
            pg.wait_for_timeout(250)
        # Add Screen with no screen to copy waits for a pick
        pg.evaluate("() => window.app.openPresetPicker()")
        pg.wait_for_timeout(400)
        st = pg.evaluate(MODAL_JS)
        assert st['mode'] == 'add' and st['defaultRow'] is None and st['disabled'] is True, st
        assert st['summary'] == 'Nothing selected. Pick a panel or a preset.', st
        pg.evaluate("() => window.app.confirmPresetPicker()")   # a forced confirm makes nothing
        pg.wait_for_timeout(400)
        assert pg.evaluate("() => window.app.project.layers.length") == 0
        assert _picker_shown(pg)
        # ...and a pick makes the first screen
        panel = pg.evaluate(PICK_PANEL_JS, [128])
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("() => window.app.project.layers.length === 1", timeout=10000)
        pg.wait_for_timeout(800)
        made = pg.evaluate(LAYER_JS, None)
        assert made['name'] == 'Screen1', made
        _expect_panel(made, panel)
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_opening_a_saved_show_never_opens_the_picker(e2e_server, pw_browser, tmp_path):
    context, pg, problems = None, None, []
    try:
        context, pg, problems = _open_page(pw_browser, e2e_server)
        pg.wait_for_timeout(1500)
        assert not _picker_shown(pg)
        show = _server_project(pg)
        show['name'] = 'Saved Show'
        show.pop('is_pristine', None)
        path = tmp_path / 'saved_show.json'
        path.write_text(json.dumps(show), encoding='utf-8')
        with pg.expect_file_chooser() as chooser:
            pg.evaluate("() => window.app.loadProjectFromFile()")
        chooser.value.set_files(str(path))
        pg.wait_for_function("() => window.app.project.name === 'Saved Show'", timeout=10000)
        pg.wait_for_timeout(2000)
        assert not _picker_shown(pg)
        # relaunching the page on the opened show does not ask either
        pg.reload(wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
        pg.wait_for_timeout(2000)
        assert pg.evaluate("() => window.app.project.name") == 'Saved Show'
        assert not _picker_shown(pg)
        assert problems == [], problems
    finally:
        if context:
            context.close()


def test_the_picker_waits_for_another_dialog(e2e_server, pw_browser):
    """It never opens over another dialog: a dialog up at launch holds it
    until it closes, and the What's New window counts as one."""
    blocker = (ENABLE_PICKER +
               "document.addEventListener('DOMContentLoaded', () => {"
               " const m = document.createElement('div'); m.id = 'test-blocker'; m.className = 'modal';"
               " m.style.display = 'block'; document.body.appendChild(m); });")
    context, pg, problems = None, None, []
    try:
        _new_pristine_project(e2e_server)
        context, pg, problems = _open_page(pw_browser, e2e_server, init=blocker)
        pg.wait_for_timeout(2000)
        assert not _picker_shown(pg)
        assert pg.evaluate("() => window.app._launchUiBusy()") is True
        pg.evaluate("() => { document.getElementById('test-blocker').style.display = 'none'; }")
        st = _wait_picker(pg)
        assert st['title'] == 'Choose a panel', st
        # the What's New window holds it the same way
        pg.evaluate("() => window.app.closePresetPicker()")
        assert pg.evaluate("() => window.app._launchUiBusy()") is False
        pg.evaluate("""() => { localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.3');
            localStorage.setItem(window.WhatsNew.MARK_KEY, '1'); window.WhatsNew.autoRun(true); }""")
        pg.wait_for_function("() => { const m = document.getElementById('whatsnew-modal');"
                             " return m && m.style.display === 'block'; }", timeout=5000)
        assert pg.evaluate("() => window.app._launchUiBusy()") is True
        pg.click('#whatsnew-close')
        assert pg.evaluate("() => window.app._launchUiBusy()") is False
        assert problems == [], problems
    finally:
        if context:
            context.close()
