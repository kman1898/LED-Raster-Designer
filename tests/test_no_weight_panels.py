"""A panel with no weight has no weight (owner, 2026-11-16).

"No weight means no weight", the way a panel with no power has no power
(test_no_power_panels.py). The panel library lists a few tiles with no
published weight: `weight_kg` null (DVS ZERA-1.5XPS / 1.9XPS) or 0.0 on
some older entries (DigiLED Pitch 10, Esdlumen EC1.9 / EC2.6, ...), which
means the same thing.

  - Every road that applies such a tile to a screen leaves it with no
    weight (panel_weight null): Add Screen, the start-up picker, Change
    cabinet, a favorite (the hearted snapshot or the library's row), and
    Add Screen's "same as the last screen". Never the server's 20 kg,
    never the screen beside it, never the old panel's figure.
  - Such a screen: Weight per Panel is empty with a note under it; the
    canvas weight line and info bar say "No weight figure"; a group's
    totals, on its row and on its label, name the screens they leave out
    ("No weight figure: Screen2").
  - Typing a weight brings it back. Emptying the box is no weight, not a
    typing mistake. A saved screen with a number keeps it, and a screen
    saved with none stays with none across a reload.
  - The picker never shows "0kg" for such a tile.
  - The binder's export warning names the screens with no power figure,
    beside the ones that cannot fit a circuit. It never names a screen
    for its weight: the binder prints no weight.

Run locally (each session takes its own free port):
    python -m pytest tests/test_no_weight_panels.py -v --browser chromium
"""

import json
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


NULL_TILE = ('DVS', 'ZERA-1.5XPS')   # weight_kg null in the library
ZERO_TILE = ('Esdlumen', 'EC1.9')    # weight_kg 0.0 in the library
WALL_KG = 20


# One screen, WALL, 20 kg a panel, 250 W, 208 V / 20 A.
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
    app.dedupeProjectLayers('no_weight_seed');
    // the browser's copy of the screen, as adding it in the app keeps it
    app.saveClientSideProperties();
    const wall = app.project.layers.find(l => l.name === 'WALL');
    app.selectLayer(wall);
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('No Weight Seed');
    return wall.id;
}"""

# A library tile by manufacturer and name, typed into the search box and
# clicked in the list, the user's way. Hands back the row's text too.
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
    const rowText = row.innerText;
    row.click();
    await new Promise(r => setTimeout(r, 50));
    const summary = document.getElementById('preset-picker-summary');
    return {weight_kg: p.weight_kg, rowText, summary: summary ? summary.textContent : ''};
}"""

# What the app shows for screen `id`: its panel_weight, client and server,
# the Weight box and its note, the screen's weight, and every text the
# canvas draws on Pixel Map with the weight line and the info bar on.
WEIGHT_VIEW_JS = """async (id) => {
    const app = window.app;
    await (app._layerSavesSettled ? app._layerSavesSettled() : Promise.resolve());
    const l = app.project.layers.find(x => x.id === id);
    app.selectLayer(l);
    app.loadLayerToInputs();
    const r = window.canvasRenderer;
    const shown = app.project.layers.map(x => [x, x.showLabelWeight, x.showLabelInfo]);
    app.project.layers.forEach(x => { x.showLabelWeight = true; x.showLabelInfo = true; });
    const texts = [];
    const ctx = r.ctx;
    const fill = ctx.fillText;
    ctx.fillText = function (t, x, y, w) { texts.push(String(t)); return fill.call(ctx, t, x, y, w); };
    try { r.render(); } finally {
        ctx.fillText = fill;
        shown.forEach(([x, w, i]) => { x.showLabelWeight = w; x.showLabelInfo = i; });
    }
    const served = (await (await fetch('/api/project')).json()).layers.find(x => x.id === id);
    const note = document.getElementById('panel-weight-note');
    const w = document.getElementById('panel-weight-kg');
    return {
        name: l.name,
        weight: l.panel_weight === undefined ? 'undefined' : l.panel_weight,
        servedWeight: served ? (served.panel_weight === undefined ? 'undefined' : served.panel_weight) : 'missing',
        field: w.value,
        invalid: w.classList.contains('invalid') || (w.validity && !w.validity.valid),
        note: note && note.style.display !== 'none' ? note.textContent : '',
        kg: app.getLayerWeightKg(l),
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
    pg.locator('[data-mode="pixel-map"]').click()
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


def _type_weight(pg, value):
    field = pg.locator('#panel-weight-kg')
    field.click()
    field.fill(value)
    field.press('Enter')
    field.blur()
    pg.wait_for_timeout(300)


def _weight_texts(view):
    return [t for t in view['texts'] if 'Weight' in t or 'weight' in t]


def _expect_no_weight(view, published=True):
    assert view['weight'] is None, view
    assert view['servedWeight'] is None, view
    assert view['field'] == '', view
    assert not view['invalid'], view
    assert view['note'] == ('No published weight for this panel. Type its weight.' if published
                            else 'No weight figure for this panel. Type its weight.'), view
    assert view['kg'] == 0, view
    # the screen's own weight line, and the info bar's part, say so
    assert 'No weight figure' in view['texts'], _weight_texts(view)


def _expect_weight(view, kg):
    assert view['weight'] == kg, view
    assert view['servedWeight'] == kg, view
    assert view['field'] == str(kg), view
    assert view['note'] == '', view
    assert view['kg'] > 0, view
    # its own weight line carries a figure (another screen on the canvas
    # may still say "No weight figure")
    assert any(t.startswith('Weight ') and t.endswith(' lb') for t in view['texts']), _weight_texts(view)


# ── Add Screen ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('tile', [NULL_TILE, ZERO_TILE], ids=['null-weight', 'zero-weight'])
def test_a_screen_added_from_a_no_weight_panel_has_no_weight(page, tile):
    pg, errors = page
    wall = _seed(pg)
    new_id, got = _add_from(pg, tile)
    assert not (got['weight_kg'] or 0), got
    # the picker's row and summary never say 0kg
    assert '0kg' not in got['rowText'] and 'kg' not in got['rowText'], got
    assert 'kg' not in got['summary'], got
    view = pg.evaluate(WEIGHT_VIEW_JS, new_id)
    # never the 20 kg screen beside it, never the server's 20 kg
    _expect_no_weight(view)
    wall_view = pg.evaluate(WEIGHT_VIEW_JS, wall)
    _expect_weight(wall_view, WALL_KG)
    assert errors == [], errors


# ── Change cabinet, and typing the weight ────────────────────────────────

def test_a_no_weight_panel_takes_the_old_panels_weight_away_and_typing_brings_it_back(page):
    pg, errors = page
    wall = _seed(pg)
    _expect_weight(pg.evaluate(WEIGHT_VIEW_JS, wall), WALL_KG)
    pg.evaluate("(id) => window.app.openChangeCabinet([window.app.project.layers.find(l => l.id === id)])", wall)
    _pick_and_confirm(pg, NULL_TILE)
    pg.wait_for_function("(id) => window.app.project.layers.find(l => l.id === id).panel_weight === null",
                         arg=wall, timeout=10000)
    _expect_no_weight(pg.evaluate(WEIGHT_VIEW_JS, wall))
    assert pg.evaluate("() => window.app.history[window.app.historyIndex].action") == 'Change Cabinet'
    # typing the weight: everything works as normal
    _type_weight(pg, '12.5')
    _expect_weight(pg.evaluate(WEIGHT_VIEW_JS, wall), 12.5)
    # emptying the box is no weight again, not a typing mistake
    _type_weight(pg, '')
    _expect_no_weight(pg.evaluate(WEIGHT_VIEW_JS, wall))
    _type_weight(pg, '9')
    _expect_weight(pg.evaluate(WEIGHT_VIEW_JS, wall), 9)
    # a weighted panel picked over it gives the weight back
    assert errors == [], errors


def test_a_zero_weight_panel_also_replaces_the_old_weight(page):
    pg, errors = page
    wall = _seed(pg)
    pg.evaluate("(id) => window.app.openChangeCabinet([window.app.project.layers.find(l => l.id === id)])", wall)
    _pick_and_confirm(pg, ZERO_TILE)
    pg.wait_for_function("(id) => window.app.project.layers.find(l => l.id === id).panel_weight === null",
                         arg=wall, timeout=10000)
    _expect_no_weight(pg.evaluate(WEIGHT_VIEW_JS, wall))
    assert errors == [], errors


def test_typing_0_weight_is_the_same_as_emptying_the_box(page):
    """Owner, 2026-11-17: "type 0 is same as blank". A 0 typed in Weight
    per Panel leaves no weight figure, exactly as an emptied box does:
    no weight stored (client and server), an empty box with its note,
    and "No weight figure" on the screen."""
    pg, errors = page
    wall = _seed(pg)
    _expect_weight(pg.evaluate(WEIGHT_VIEW_JS, wall), WALL_KG)
    _type_weight(pg, '0')
    zero = pg.evaluate(WEIGHT_VIEW_JS, wall)
    _expect_no_weight(zero, published=False)
    _type_weight(pg, '15')
    _expect_weight(pg.evaluate(WEIGHT_VIEW_JS, wall), 15)
    _type_weight(pg, '')
    blank = pg.evaluate(WEIGHT_VIEW_JS, wall)
    _expect_no_weight(blank, published=False)
    for k in ('weight', 'servedWeight', 'field', 'note', 'kg'):
        assert zero[k] == blank[k], (k, zero[k], blank[k])
    assert errors == [], errors


def test_a_no_weight_screen_changes_its_unit_without_inventing_a_weight(page):
    pg, errors = page
    wall = _seed(pg)
    pg.evaluate("(id) => window.app.openChangeCabinet([window.app.project.layers.find(l => l.id === id)])", wall)
    _pick_and_confirm(pg, NULL_TILE)
    pg.wait_for_function("(id) => window.app.project.layers.find(l => l.id === id).panel_weight === null",
                         arg=wall, timeout=10000)
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(l => l.id === id))", wall)
    pg.select_option('#panel-weight-unit', 'lb')
    pg.wait_for_timeout(300)
    view = pg.evaluate(WEIGHT_VIEW_JS, wall)
    assert pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).weight_unit", wall) == 'lb'
    _expect_no_weight(view)
    assert errors == [], errors


# ── favorites and "same as the last screen" ──────────────────────────────

def test_a_favorite_and_the_last_screens_panel_carry_no_weight(page):
    pg, errors = page
    _seed(pg)
    # a favorite of a library tile with none, and one the library no
    # longer has whose snapshot carries 0
    gone = {'_mfr': 'Esdlumen', 'name': 'Retired No Weight Tile', 'width_mm': 500, 'height_mm': 500,
            'pixels_w': 160, 'pixels_h': 160, 'weight_kg': 0.0, 'watts_max': 150.0}
    favs = [{'_mfr': ZERO_TILE[0], 'name': ZERO_TILE[1], 'width_mm': 250, 'height_mm': 500,
             'pixels_w': 128, 'pixels_h': 256, 'weight_kg': 0.0, 'watts_max': 81.4}, gone]
    pg.evaluate("(f) => { window.app.setAddLayerFavorites(f); window.app.setAddLayerOrder([]); }", favs)
    try:
        for fav in favs:
            key = f"{fav['_mfr']}|{fav['name']}"
            before = _layer_ids(pg)
            pg.evaluate("() => window.app.openPresetPicker()")
            row = pg.locator(f'#preset-picker-list .preset-picker-row[data-kind="favorite"][data-key="{key}"]')
            row.wait_for(timeout=10000)
            # the row shows no weight for it
            assert 'kg' not in row.inner_text(), row.inner_text()
            row.click()
            pg.locator('#preset-picker-add').click()
            pg.wait_for_function("(n) => window.app.project.layers.length === n + 1",
                                 arg=len(before), timeout=10000)
            new_id = [i for i in _layer_ids(pg) if i not in before][0]
            view = pg.evaluate(WEIGHT_VIEW_JS, new_id)
            assert view['weight'] is None and view['servedWeight'] is None, (fav, view)
            assert view['note'], (fav, view)
        # Add Screen with nothing picked copies the last screen's panel:
        # no weight, never the 20 kg screen's or the server's
        before = _layer_ids(pg)
        pg.evaluate("() => window.app.openPresetPicker()")
        pg.wait_for_selector('#preset-picker-list .preset-picker-row[data-kind="default"]', timeout=10000)
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("(n) => window.app.project.layers.length === n + 1", arg=len(before), timeout=10000)
        new_id = [i for i in _layer_ids(pg) if i not in before][0]
        view = pg.evaluate(WEIGHT_VIEW_JS, new_id)
        assert view['weight'] is None and view['servedWeight'] is None, view
    finally:
        pg.evaluate("() => { window.app.setAddLayerFavorites([]); }")
    assert errors == [], errors


# ── a preset saved from a no-weight screen ───────────────────────────────

def test_a_preset_that_says_no_weight_gives_no_weight(page):
    pg, errors = page
    _seed(pg)
    before = _layer_ids(pg)
    pg.evaluate("""() => window.app.addLayer({columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 128,
        panel_width_mm: 500, panel_height_mm: 500, panel_weight: null, weight_unit: 'kg',
        panelWatts: 100, _presetName: 'no weight preset'})""")
    pg.wait_for_function("(n) => window.app.project.layers.length === n + 1", arg=len(before), timeout=10000)
    new_id = [i for i in _layer_ids(pg) if i not in before][0]
    view = pg.evaluate(WEIGHT_VIEW_JS, new_id)
    assert view['weight'] is None and view['servedWeight'] is None, view
    assert view['note'] == 'No weight figure for this panel. Type its weight.', view
    assert errors == [], errors


def test_a_saved_preset_with_no_weight_or_watts_at_all_gives_none(page):
    """Owner, 2026-11-17: a preset saved with no weight or watts key (a
    very old one, or one edited by hand) lands as no weight figure and no
    power figure: never 20 kg, the screen beside it's, the Preferences'
    watts or the old panel's. Both for a screen it makes and for a
    Change cabinet."""
    pg, errors = page
    wall = _seed(pg)
    name = 'Old Preset Without Figures'
    data = {'columns': 2, 'rows': 2, 'cabinet_width': 160, 'cabinet_height': 160,
            'panel_width_mm': 500, 'panel_height_mm': 500}
    pg.evaluate("""async ([n, d]) => { await fetch('/api/presets/' + encodeURIComponent(n), {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({data: d})}); }""", [name, data])
    row = f'#preset-picker-list .preset-picker-row[data-key="{name}"]'
    figures = """async (id) => {
        const app = window.app;
        await (app._layerSavesSettled ? app._layerSavesSettled() : Promise.resolve());
        const l = app.project.layers.find(x => x.id === id);
        const s = (await (await fetch('/api/project')).json()).layers.find(x => x.id === id);
        const v = (o, k) => (o[k] === undefined ? 'undefined' : o[k]);
        return {weight: v(l, 'panel_weight'), watts: v(l, 'panelWatts'), cw: l.cabinet_width,
                servedWeight: v(s, 'panel_weight'), servedWatts: v(s, 'panelWatts')};
    }"""
    try:
        # Add Screen from it
        before = _layer_ids(pg)
        pg.evaluate("() => window.app.openPresetPicker()")
        pg.wait_for_selector(row, timeout=5000)
        pg.locator(row).click()
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("(n) => window.app.project.layers.length === n + 1", arg=len(before), timeout=10000)
        new_id = [i for i in _layer_ids(pg) if i not in before][0]
        got = pg.evaluate(figures, new_id)
        assert got == {'weight': None, 'watts': None, 'cw': 160, 'servedWeight': None, 'servedWatts': None}, got
        _expect_no_weight(pg.evaluate(WEIGHT_VIEW_JS, new_id), published=False)
        # Change cabinet to it: the 20 kg, 250 W wall keeps neither
        pg.evaluate("(id) => window.app.openChangeCabinet([window.app.project.layers.find(l => l.id === id)])", wall)
        pg.wait_for_selector(row, timeout=5000)
        pg.locator(row).click()
        pg.locator('#preset-picker-add').click()
        pg.wait_for_function("(id) => window.app.project.layers.find(l => l.id === id).cabinet_width === 160",
                             arg=wall, timeout=10000)
        got = pg.evaluate(figures, wall)
        assert got == {'weight': None, 'watts': None, 'cw': 160, 'servedWeight': None, 'servedWatts': None}, got
    finally:
        pg.evaluate("(n) => fetch('/api/presets/' + encodeURIComponent(n), {method: 'DELETE'})", name)
    assert errors == [], errors


# ── the totals name the screens they leave out ───────────────────────────

GROUP_JS = """async ([a, b]) => {
    const app = window.app;
    // the same processor and power settings, so grouping asks nothing
    const [la, lb] = [a, b].map(id => app.project.layers.find(l => l.id === id));
    ['processorType', 'bitDepth', 'frameRate', 'lowLatency', 'powerVoltage', 'powerVoltageCustom',
     'powerAmperage', 'powerAmperageCustom'].forEach(k => { lb[k] = la[k]; });
    await app.updateLayers([lb]);
    await (app._layerSavesSettled ? app._layerSavesSettled() : Promise.resolve());
    app.selectedLayerIds = new Set([a, b]);
    app.currentLayer = la;
    const gid = await Promise.race([app.groupSelectedLayers(),
        new Promise(r => setTimeout(() => r('timed out'), 8000))]);
    if (gid === 'timed out' || gid == null) return {gid};
    await (app._layerSavesSettled ? app._layerSavesSettled() : Promise.resolve());
    await new Promise(r => setTimeout(r, 300));
    const group = app.project.groups.find(g => g.id === gid);
    const totals = app.getGroupTotals(group);
    return {line: app.formatGroupTotalsLine(group), weightUnset: totals.weightUnset,
            weightKg: totals.weightKg};
}"""


def test_a_groups_totals_name_the_screen_with_no_weight(page):
    pg, errors = page
    wall = _seed(pg)
    new_id, _ = _add_from(pg, NULL_TILE)
    name = pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).name", new_id)
    got = pg.evaluate(GROUP_JS, [wall, new_id])
    assert 'line' in got, got
    assert got['weightUnset'] == [new_id], got
    # only WALL's 12 cabinets at 20 kg are weighed
    assert abs(got['weightKg'] - 12 * WALL_KG) < 1e-6, got
    assert f'No weight figure: {name}' in got['line'], got
    # the group's label on the canvas names it too
    view = pg.evaluate(WEIGHT_VIEW_JS, wall)
    assert any(f'No weight figure: {name}' in t for t in view['texts']), _weight_texts(view)
    assert errors == [], errors


# ── the binder's export warning ──────────────────────────────────────────

WARN_JS = """() => {
    const app = window.app;
    return app.binderCannotFitWarning(Object.assign(app.readBinderOptions(),
        { scope: { kind: 'show' }, sides: { power: true, data: false } }));
}"""


def test_the_binder_warning_names_no_power_but_never_weight(page):
    pg, errors = page
    wall = _seed(pg)
    # no weight (power listed): DVS ZERA-1.5XPS
    no_weight, _ = _add_from(pg, NULL_TILE)
    # no power, with weight: the WALL's power emptied
    pg.evaluate("""async (id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        l.panelWatts = null;
        await app.updateLayers([l]);
    }""", wall)
    names = pg.evaluate("(ids) => ids.map(id => window.app.project.layers.find(l => l.id === id).name)",
                        [wall, no_weight])
    warn = pg.evaluate(WARN_JS)
    assert f'This screen has no power figure: {names[0]}. Type its watts in Power Settings.' in warn, warn
    assert 'weight' not in warn and names[1] not in warn, warn
    assert ' - ' not in warn and '—' not in warn and '–' not in warn, warn
    # with the watts in, the warning is empty though one screen has no weight
    pg.evaluate("""async (id) => {
        const app = window.app;
        const a = app.project.layers.find(x => x.id === id);
        a.panelWatts = 250;
        await app.updateLayers([a]);
    }""", wall)
    assert pg.evaluate(WARN_JS) == '', pg.evaluate(WARN_JS)
    assert errors == [], errors


# ── a saved show keeps its weight ────────────────────────────────────────

def test_a_saved_weight_and_a_saved_no_weight_both_survive_a_reload(page):
    pg, errors = page
    wall = _seed(pg)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.wait_for_timeout(400)
    _expect_weight(pg.evaluate(WEIGHT_VIEW_JS, wall), WALL_KG)
    pg.evaluate("(id) => window.app.selectLayer(window.app.project.layers.find(x => x.id === id))", wall)
    _type_weight(pg, '')
    pg.evaluate("async () => { await (window.app._layerSavesSettled ? window.app._layerSavesSettled() : null); }")
    pg.wait_for_timeout(300)
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)", timeout=20000)
    pg.wait_for_timeout(400)
    _expect_no_weight(pg.evaluate(WEIGHT_VIEW_JS, wall), published=False)
    assert errors == [], errors


# ── the start-up picker ──────────────────────────────────────────────────

def test_the_startup_pick_of_a_no_weight_panel_has_no_weight(e2e_server, pw_browser):
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
        _pick_and_confirm(pg, ZERO_TILE)
        pg.wait_for_function("(id) => window.app.project.layers.length === 1"
                             " && window.app.project.layers[0].id !== id"
                             " && window.app.project.layers[0].panelModelName", arg=startup_id, timeout=10000)
        new_id = pg.evaluate("() => window.app.project.layers[0].id")
        _expect_no_weight(pg.evaluate(WEIGHT_VIEW_JS, new_id))
        assert errors == [], errors
    finally:
        context.close()
