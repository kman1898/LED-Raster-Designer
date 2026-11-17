"""A panel with no power has no power (owner, 2026-11-16).

"panels with no power have no power". The panel library lists some tiles
with no published power: `watts_max` null (Dicolor's V2 and UL tiles), or
0.0 on a few older entries (DigiLED MC15 / MK10 / MK5, UniLumin
UtileIII03 / 04 / 05 / 07), which means the same thing.

  - Every road that applies a library tile to a screen leaves it with no
    panel power (panelWatts null) when the tile has none: Add Screen, the
    start-up picker, Change cabinet, a favorite (the hearted snapshot or
    the library's row), and Add Screen's "same as the last screen". Never
    the Preferences' watts or the server's default, and never the old
    panel's figure (app-presets.js _panelToPresetData, _cabinetFieldsFrom,
    _lastScreenPanelData).
  - Such a screen: Watts per Panel is empty with a note under it; the
    Power tab's readout shows "-" for panels a circuit, circuits and amps;
    the canvas says "No power figure" on the screen; no circuits are
    made. The totals name the screens they leave out ("No power figure:
    Screen2"), never counting them as a quiet 0.
  - Typing watts brings everything back. Emptying the box is no power,
    not a typing mistake.
  - A saved screen that already has a number keeps it.

Run locally (each session takes its own free port):
    python -m pytest tests/test_no_power_panels.py -v --browser chromium
"""

import json
import os
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


NULL_TILE = ('Dicolor', 'UL 1.9')   # watts_max null in the library
ZERO_TILE = ('DigiLED', 'MK5')      # watts_max 0.0 in the library
POWER_TILE_WATTS = 250


# One screen, WALL, 250 W a panel, 208 V / 20 A.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    await (app._layerSavesSettled ? app._layerSavesSettled() : Promise.resolve());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'WALL', columns: 4, rows: 3,
        cabinet_width: 200, cabinet_height: 200, panel_width_mm: 500, panel_height_mm: 500,
        panel_weight: 20, weight_unit: 'kg', panelWatts: 250, powerVoltage: 208,
        powerVoltageCustom: 208, powerAmperage: 20, powerAmperageCustom: 20,
        offset_x: 0, offset_y: 0, flowPattern: 'tl-h'});
    const p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('no_power_seed');
    const wall = app.project.layers.find(l => l.name === 'WALL');
    app.selectLayer(wall);
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('No Power Seed');
    return wall.id;
}"""

# A library tile by manufacturer and name, typed into the search box and
# clicked in the list, the user's way.
PICK_JS = """async ([mfr, name]) => {
    const app = window.app;
    for (let i = 0; i < 200 && !(app._panelCatalogFlat && app._panelCatalogFlat.length); i++) {
        await new Promise(r => setTimeout(r, 50));
    }
    const p = app._panelCatalogFlat.find(x => x._mfr === mfr && x.name === name);
    if (!p) return null;
    const search = document.getElementById('panel-catalog-search');
    search.value = name;
    search.dispatchEvent(new Event('input', {bubbles: true}));
    let row = null;
    for (let i = 0; i < 100 && !row; i++) {
        await new Promise(r => setTimeout(r, 50));
        row = [...document.querySelectorAll('#panel-catalog-list .panel-catalog-row')]
            .find(el => el.dataset.mfr === mfr && el.dataset.name === name) || null;
    }
    if (!row) return null;
    row.click();
    return {watts_max: p.watts_max, pixels_w: p.pixels_w};
}"""

# What the app shows for screen `id` on the Power tab: the screen's
# panelWatts, client and server, the Watts box and its note, the readout,
# the circuits made, and every text the canvas draws in one frame.
POWER_VIEW_JS = """async (id) => {
    const app = window.app;
    await (app._layerSavesSettled ? app._layerSavesSettled() : Promise.resolve());
    const l = app.project.layers.find(x => x.id === id);
    app.selectLayer(l);
    app.loadLayerToInputs();
    app.refreshTotalsSidebar();
    const r = window.canvasRenderer;
    const texts = [];
    const ctx = r.ctx;
    const fill = ctx.fillText;
    ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return fill.call(ctx, t, x, y, w); };
    try { r.render(); } finally { ctx.fillText = fill; }
    const served = (await (await fetch('/api/project')).json()).layers.find(x => x.id === id);
    const note = document.getElementById('power-panel-watts-note');
    const unset = document.getElementById('power-totals-project-unset');
    const w = document.getElementById('power-panel-watts');
    return {
        name: l.name,
        panelWatts: l.panelWatts === undefined ? 'undefined' : l.panelWatts,
        servedWatts: served ? (served.panelWatts === undefined ? 'undefined' : served.panelWatts) : 'missing',
        field: w.value,
        invalid: w.classList.contains('invalid'),
        note: note && note.style.display !== 'none' ? note.textContent : '',
        panelsPerCircuit: document.getElementById('power-panels-per-circuit').textContent,
        circuitsRequired: document.getElementById('power-circuits-required').textContent,
        amps1: document.getElementById('power-total-amps-1ph').textContent,
        amps3: document.getElementById('power-total-amps-3ph').textContent,
        circuits: (app.calculatePowerAssignments(l).circuits || []).length,
        counted: app.screenCircuitCount(l),
        totalsUnset: unset && unset.style.display !== 'none' ? unset.textContent : '',
        counts: app.getPowerCounts(),
        texts,
    };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');"
        "localStorage.removeItem('addLayer.favorites');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    yield pg, errors
    context.close()


def _seed(pg):
    wall = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(300)
    return wall


def _layer_ids(pg):
    return pg.evaluate("() => window.app.project.layers.map(l => l.id)")


def _pick_and_confirm(pg, tile):
    pg.wait_for_selector('#panel-catalog-list .panel-catalog-row', timeout=15000)
    got = pg.evaluate(PICK_JS, list(tile))
    assert got is not None, f'{tile} is not in the panel library'
    pg.locator('#preset-picker-add').click()
    return got


def _add_from(pg, tile):
    before = _layer_ids(pg)
    pg.evaluate("() => window.app.openPresetPicker()")
    got = _pick_and_confirm(pg, tile)
    pg.wait_for_function("(n) => window.app.project.layers.length === n + 1", arg=len(before), timeout=10000)
    new_id = [i for i in _layer_ids(pg) if i not in before][0]
    return new_id, got


def _type_watts(pg, value):
    field = pg.locator('#power-panel-watts')
    field.click()
    field.fill(value)
    field.press('Enter')
    pg.wait_for_timeout(300)


def _expect_no_power(view, published=True):
    assert view['panelWatts'] is None, view
    assert view['servedWatts'] is None, view
    assert view['field'] == '', view
    assert not view['invalid'], view
    assert view['note'] == ('No published power for this panel. Type its watts.' if published
                            else 'No power figure for this panel. Type its watts.'), view
    assert view['panelsPerCircuit'] == '-', view
    assert view['circuitsRequired'] == '-', view
    assert view['amps1'] == '-' and view['amps3'] == '-', view
    assert view['circuits'] == 0 and view['counted'] == 0, view
    assert 'No power figure' in view['texts'], view['texts']
    assert view['totalsUnset'] == f"No power figure: {view['name']}", view
    assert view['counts']['wattsUnset'], view['counts']


def _expect_power(view, watts):
    assert view['panelWatts'] == watts, view
    assert view['servedWatts'] == watts, view
    assert view['field'] == str(watts), view
    assert view['note'] == '', view
    assert view['panelsPerCircuit'] not in ('-', '0'), view
    assert view['circuitsRequired'] not in ('-', '0'), view
    assert view['amps3'].endswith(' A'), view
    assert view['circuits'] > 0, view
    assert 'No power figure' not in view['texts'], view['texts']
    assert view['totalsUnset'] == '', view


# ── Add Screen ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('tile', [NULL_TILE, ZERO_TILE], ids=['null-watts', 'zero-watts'])
def test_a_screen_added_from_a_no_power_panel_has_no_power(page, tile):
    pg, errors = page
    wall = _seed(pg)
    new_id, got = _add_from(pg, tile)
    assert not (got['watts_max'] or 0), got
    view = pg.evaluate(POWER_VIEW_JS, new_id)
    _expect_no_power(view)
    # the 250 W screen beside it is untouched, and the totals leave the
    # new one out by name rather than as a quiet 0
    wall_view = pg.evaluate(POWER_VIEW_JS, wall)
    assert wall_view['panelWatts'] == POWER_TILE_WATTS and wall_view['circuits'] > 0, wall_view
    assert wall_view['totalsUnset'] == f"No power figure: {view['name']}", wall_view
    assert errors == [], errors


# ── Change cabinet, and typing the watts ─────────────────────────────────

def test_a_no_power_panel_takes_the_old_panels_power_away_and_typing_brings_it_back(page):
    pg, errors = page
    wall = _seed(pg)
    before = pg.evaluate(POWER_VIEW_JS, wall)
    _expect_power(before, POWER_TILE_WATTS)
    pg.evaluate("(id) => window.app.openChangeCabinet([window.app.project.layers.find(l => l.id === id)])", wall)
    _pick_and_confirm(pg, NULL_TILE)
    pg.wait_for_function("(id) => window.app.project.layers.find(l => l.id === id).panelWatts === null",
                         arg=wall, timeout=10000)
    _expect_no_power(pg.evaluate(POWER_VIEW_JS, wall))
    # one Change Cabinet step in the history
    assert pg.evaluate("() => window.app.history[window.app.historyIndex].action") == 'Change Cabinet'
    # typing the watts: everything works as normal
    _type_watts(pg, '300')
    _expect_power(pg.evaluate(POWER_VIEW_JS, wall), 300)
    # emptying the box is no power again, not a typing mistake
    _type_watts(pg, '')
    view = pg.evaluate(POWER_VIEW_JS, wall)
    _expect_no_power(view)
    _type_watts(pg, '200+50')
    _expect_power(pg.evaluate(POWER_VIEW_JS, wall), 250)
    assert errors == [], errors


def test_typing_0_watts_is_the_same_as_emptying_the_box(page):
    """Owner, 2026-11-17: "type 0 is same as blank". A 0 typed in Watts
    per Panel leaves no power figure, exactly as an emptied box does: no
    watts stored (client and server), an empty box with its note, no
    circuits, and the totals name the screen."""
    pg, errors = page
    wall = _seed(pg)
    _expect_power(pg.evaluate(POWER_VIEW_JS, wall), POWER_TILE_WATTS)
    _type_watts(pg, '0')
    zero = pg.evaluate(POWER_VIEW_JS, wall)
    _expect_no_power(zero, published=False)
    _type_watts(pg, '300')
    _expect_power(pg.evaluate(POWER_VIEW_JS, wall), 300)
    _type_watts(pg, '')
    blank = pg.evaluate(POWER_VIEW_JS, wall)
    _expect_no_power(blank, published=False)
    for k in ('panelWatts', 'servedWatts', 'field', 'note', 'circuits', 'totalsUnset'):
        assert zero[k] == blank[k], (k, zero[k], blank[k])
    assert errors == [], errors


def test_a_zero_watt_panel_also_replaces_the_old_power(page):
    pg, errors = page
    wall = _seed(pg)
    pg.evaluate("(id) => window.app.openChangeCabinet([window.app.project.layers.find(l => l.id === id)])", wall)
    _pick_and_confirm(pg, ZERO_TILE)
    pg.wait_for_function("(id) => window.app.project.layers.find(l => l.id === id).panelWatts === null",
                         arg=wall, timeout=10000)
    _expect_no_power(pg.evaluate(POWER_VIEW_JS, wall))
    assert errors == [], errors


# ── favorites and "same as the last screen" ──────────────────────────────

def test_a_favorite_and_the_last_screens_panel_carry_no_power(page):
    pg, errors = page
    _seed(pg)
    # a favorite of a library tile with none, and one the library no
    # longer has whose snapshot carries 0
    gone = {'_mfr': 'Dicolor', 'name': 'Retired No Power Tile', 'width_mm': 500, 'height_mm': 500,
            'pixels_w': 160, 'pixels_h': 160, 'weight_kg': 7.0, 'watts_max': 0.0}
    favs = [{'_mfr': ZERO_TILE[0], 'name': ZERO_TILE[1], 'width_mm': 500, 'height_mm': 500,
             'pixels_w': 96, 'pixels_h': 96, 'weight_kg': 10.0, 'watts_max': 0.0}, gone]
    pg.evaluate("(f) => { window.app.setAddLayerFavorites(f); window.app.setAddLayerOrder([]); }", favs)
    try:
        for fav in favs:
            key = f"{fav['_mfr']}|{fav['name']}"
            before = _layer_ids(pg)
            pg.evaluate("() => window.app.openPresetPicker()")
            row = pg.locator(f'#preset-picker-list .preset-picker-row[data-kind="favorite"][data-key="{key}"]')
            row.wait_for(timeout=10000)
            # the row shows no watts for it
            assert 'W/panel' not in row.inner_text(), row.inner_text()
            row.click()
            pg.locator('#preset-picker-add').click()
            pg.wait_for_function("(n) => window.app.project.layers.length === n + 1",
                                 arg=len(before), timeout=10000)
            new_id = [i for i in _layer_ids(pg) if i not in before][0]
            view = pg.evaluate(POWER_VIEW_JS, new_id)
            assert view['panelWatts'] is None and view['servedWatts'] is None, (fav, view)
            assert view['note'], (fav, view)
        # Add Screen with nothing picked copies the last screen's panel:
        # no power, never the Preferences' watts
        before = _layer_ids(pg)
        pg.evaluate("() => window.app.openPresetPicker()")
        pg.wait_for_selector('#preset-picker-list .preset-picker-row[data-kind="default"]', timeout=10000)
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("(n) => window.app.project.layers.length === n + 1", arg=len(before), timeout=10000)
        new_id = [i for i in _layer_ids(pg) if i not in before][0]
        view = pg.evaluate(POWER_VIEW_JS, new_id)
        assert view['panelWatts'] is None and view['servedWatts'] is None, view
        # the totals name every screen they leave out
        names = pg.evaluate("() => window.app.project.layers.filter(l => l.panelWatts == null).map(l => l.name)")
        assert len(names) == 3, names
        assert view['totalsUnset'] == 'No power figure: ' + ', '.join(names), view
    finally:
        pg.evaluate("() => { window.app.setAddLayerFavorites([]); }")
    assert errors == [], errors


# ── a saved show keeps its watts ─────────────────────────────────────────

def test_a_saved_screen_with_watts_keeps_them_on_reload(page, e2e_server):
    pg, errors = page
    wall = _seed(pg)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    _expect_power(pg.evaluate(POWER_VIEW_JS, wall), POWER_TILE_WATTS)
    # and a screen saved with no power stays with none across a reload
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(x => x.id === id))", wall)
    _type_watts(pg, '')
    pg.evaluate("async () => { await (window.app._layerSavesSettled ? window.app._layerSavesSettled() : null); }")
    pg.wait_for_timeout(300)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    _expect_no_power(pg.evaluate(POWER_VIEW_JS, wall), published=False)
    assert errors == [], errors


# ── the start-up picker ──────────────────────────────────────────────────

def test_the_startup_pick_of_a_no_power_panel_has_no_power(e2e_server, pw_browser):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(e2e_server + '/api/project/new', data=b'', method='POST')
    with opener.open(req, timeout=10) as reply:
        assert json.loads(reply.read().decode('utf-8'))['is_pristine'] is True
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
        "window.__lrdStartupPicker = true;")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
        pg.wait_for_function(
            "() => document.getElementById('preset-picker-modal').style.display === 'block'"
            " && window.app._pickerMode === 'startup'", timeout=10000)
        startup_id = pg.evaluate("() => window.app.project.layers[0].id")
        _pick_and_confirm(pg, NULL_TILE)
        pg.wait_for_function("(id) => window.app.project.layers.length === 1"
                             " && window.app.project.layers[0].id !== id"
                             " && window.app.project.layers[0].panelModelName", arg=startup_id, timeout=10000)
        new_id = pg.evaluate("() => window.app.project.layers[0].id")
        pg.locator('[data-mode="power"]').click()
        pg.wait_for_timeout(400)
        _expect_no_power(pg.evaluate(POWER_VIEW_JS, new_id))
        assert errors == [], errors
    finally:
        context.close()


# ── the wiring ───────────────────────────────────────────────────────────

def test_the_note_and_the_totals_line_are_in_the_page():
    with open(os.path.join(ROOT, 'src', 'templates', 'index.html'), encoding='utf-8') as fh:
        html = fh.read()
    assert 'id="power-panel-watts-note"' in html
    assert 'id="power-totals-project-unset"' in html
