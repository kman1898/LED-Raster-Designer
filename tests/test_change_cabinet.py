"""Change cabinet…: re-pick a screen's cabinet, keep the screen.

"we need a change screen function, aka change to a different panel type
from the list. Maybe a right click and an option on the left of the
eyeball for the screen allows you to re-choose your panel type" (user,
2026-09-16).

  - Two ways in, one modal. The ▦ button left of the eye on a Screens
    panel row (app-layers-panel.js) opens the preset picker in replace
    mode over that row's screen; "Change cabinet…" on the right-click
    menu - a screen on the canvas or a Screens panel row
    (app-context-menu.js _prepareChangeCabinetMenu) - opens it over every
    selected screen layer. Image and text layers have no cabinet: no
    button, and a selection of only those gets no item.
  - Replace mode (app-presets.js openPresetPicker / _setPickerChrome):
    the heading reads "Change cabinet for <name>" or "for N screens",
    the confirm button "Change"; the add-mode chrome comes back for the
    next + Add Screen.
  - The write (changeCabinetForLayers): ONLY the cabinet figures land -
    cabinet_width / cabinet_height (px), panel_width_mm / panel_height_mm,
    panel_weight + weight_unit, panelWatts where the source has one. A
    saved preset carries a whole layer; its columns, rows, name, offsets,
    ports and patterns are dropped on the floor. A grouped screen changes
    alone (per-cabinet figures never travel between members). A screen
    sized by wall dimensions re-derives its columns and rows from the new
    cabinet, as a hand edit of the cabinet fields does. One PUT batch and
    one 'Change Cabinet' history entry for the whole selection; the
    server rebuilds the panels and the echo lands them.

Run locally (each session takes its own free port, so it runs beside
any other):
    python3 -m pytest tests/test_change_cabinet.py -v --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

import app as app_module  # noqa: E402,F401


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the wiring (new files must not rot) ──────────────────────────────────

def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
        return fh.read()


def test_the_pieces_are_wired():
    main_js = _src('src', 'static', 'js', 'main.js')
    for name in ('app-presets.js', 'app-context-menu.js', 'app-layers-panel.js'):
        assert f"import './{name}';" in main_js, name
    presets = _src('src', 'static', 'js', 'app-presets.js')
    for fn in ('openChangeCabinet(', 'changeCabinetForLayers(', '_cabinetFieldsFrom(',
               '_preferencesCabinetData(', '_setPickerChrome(', '_wireChangeCabinetMenuItem()'):
        assert fn in presets, fn
    menu = _src('src', 'static', 'js', 'app-context-menu.js')
    for fn in ('_prepareChangeCabinetMenu(', '_wireChangeCabinetMenuItem(', 'runChangeCabinetMenu('):
        assert fn in menu, fn
    rows = _src('src', 'static', 'js', 'app-layers-panel.js')
    assert 'layer-cabinet-btn' in rows and 'openChangeCabinet([layer])' in rows
    html = _src('src', 'templates', 'index.html')
    for marker in ('id="preset-picker-title"', 'id="preset-picker-subtitle"',
                   'data-action="change-cabinet"', 'data-label="Change cabinet…"'):
        assert marker in html, marker


# ── the browser ───────────────────────────────────────────────────────────

# Three screens: WALL-A and WALL-B grouped (a partner that must not move),
# CENTER on its own. Distinct cabinets so a change is visible from every
# field.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    delete proj.port_assignments; delete proj.pullSheet;
    await j('PUT', '/api/project', proj);
    const add = (body) => j('POST', '/api/layer/add', body);
    await add({name: 'WALL-A', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               panel_width_mm: 500, panel_height_mm: 500, panel_weight: 20, weight_unit: 'kg',
               panelWatts: 200, offset_x: 0, offset_y: 0, flowPattern: 'tl-h'});
    await add({name: 'WALL-B', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               panel_width_mm: 500, panel_height_mm: 500, panel_weight: 20, weight_unit: 'kg',
               panelWatts: 200, offset_x: 1000, offset_y: 0, flowPattern: 'tl-h'});
    await add({name: 'CENTER', columns: 3, rows: 5, cabinet_width: 128, cabinet_height: 128,
               panel_width_mm: 250, panel_height_mm: 250, panel_weight: 8, weight_unit: 'kg',
               panelWatts: 100, offset_x: 0, offset_y: 1000, flowPattern: 'tl-v'});
    let p = await j('GET', '/api/project');
    const A = p.layers.find(l => l.name === 'WALL-A');
    const B = p.layers.find(l => l.name === 'WALL-B');
    const C = p.layers.find(l => l.name === 'CENTER');
    p.groups = [{id: 'g1', name: 'SR', layer_ids: [A.id, B.id], routeDataAsOne: false}];
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('change_cabinet_setup');
    app.selectLayer(app.project.layers.find(l => l.id === C.id));
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Change Cabinet Seed');
    return {a: A.id, b: B.id, c: C.id};
}"""

# The screen as the app holds it: the cabinet figures and the fields a
# change must leave alone.
FIELDS_JS = """(id) => {
    const l = window.app.project.layers.find(x => x.id === id);
    return {
        name: l.name, columns: l.columns, rows: l.rows,
        cabinet_width: l.cabinet_width, cabinet_height: l.cabinet_height,
        panel_width_mm: l.panel_width_mm, panel_height_mm: l.panel_height_mm,
        panel_weight: l.panel_weight, weight_unit: l.weight_unit, panelWatts: l.panelWatts,
        offset_x: l.offset_x, offset_y: l.offset_y, group_id: l.group_id || null,
        flowPattern: l.flowPattern, panels: l.panels.length,
        panel0: [l.panels[0].width, l.panels[0].height],
    };
}"""

# The same screen as the server holds it.
SERVED_JS = """async (id) => {
    const p = await (await fetch('/api/project')).json();
    const l = p.layers.find(x => x.id === id);
    return {
        name: l.name, columns: l.columns, rows: l.rows,
        cabinet_width: l.cabinet_width, cabinet_height: l.cabinet_height,
        panel_width_mm: l.panel_width_mm, panel_height_mm: l.panel_height_mm,
        panel_weight: l.panel_weight, weight_unit: l.weight_unit, panelWatts: l.panelWatts,
        offset_x: l.offset_x, offset_y: l.offset_y, group_id: l.group_id || null,
        flowPattern: l.flowPattern, panels: l.panels.length,
        panel0: [l.panels[0].width, l.panels[0].height],
    };
}"""

MODAL_JS = """() => {
    const modal = document.getElementById('preset-picker-modal');
    return {
        shown: modal.style.display === 'block',
        title: document.getElementById('preset-picker-title').textContent,
        brief: document.getElementById('preset-picker-subtitle').textContent,
        confirm: document.getElementById('preset-picker-add').textContent,
        mode: window.app._pickerMode || null,
        targets: [...(window.app._pickerTargetIds || [])].sort((a, b) => a - b),
    };
}"""

MENU_JS = """() => {
    const menu = document.getElementById('context-menu');
    const item = menu.querySelector('[data-action="change-cabinet"]');
    return {
        menuShown: menu.style.display === 'block',
        shown: getComputedStyle(item).display !== 'none',
        label: item.textContent.trim(),
        selected: [...window.app.selectedLayerIds].sort((a, b) => a - b),
    };
}"""

# A client point on a screen's first cabinet (test_beaches LAYER_POINT_JS).
LAYER_POINT_JS = """(layerId) => {
    const app = window.app;
    const r = window.canvasRenderer;
    const layer = app.project.layers.find(l => l.id === layerId);
    const p = layer.panels[0];
    const {dx, dy} = r.getLayerRenderOffset(layer);
    const off = r._layerCanvasOffset(layer);
    const wx = p.x + p.width / 2 + dx + off.wx;
    const wy = p.y + p.height / 2 + dy + off.wy;
    const rect = r.canvas.getBoundingClientRect();
    const x = rect.left + wx * r.zoom + r.panX;
    const y = rect.top + wy * r.zoom + r.panY;
    return {x, y, inside: x > rect.left && x < rect.right && y > rect.top && y < rect.bottom};
}"""

# A catalog panel whose pixels differ from every seeded cabinet and that
# carries every figure the change writes, found in the loaded catalog;
# typed into the search box and clicked in the list, the user's way.
PICK_PANEL_JS = """async (avoidPx) => {
    const app = window.app;
    const p = app._panelCatalogFlat.find(x => x.pixels_w && x.pixels_h && x.width_mm && x.height_mm
        && x.weight_kg != null && x.watts_max != null && !avoidPx.includes(x.pixels_w) && x.name);
    const search = document.getElementById('panel-catalog-search');
    search.value = p.name;
    search.dispatchEvent(new Event('input', {bubbles: true}));
    await new Promise(r => setTimeout(r, 400));
    const row = [...document.querySelectorAll('#panel-catalog-list .panel-catalog-row')]
        .find(el => el.dataset.mfr === p._mfr && el.dataset.name === p.name);
    row.click();
    return {mfr: p._mfr, name: p.name, pixels_w: p.pixels_w, pixels_h: p.pixels_h,
            width_mm: p.width_mm, height_mm: p.height_mm, weight_kg: p.weight_kg, watts_max: p.watts_max};
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="pixel-map"]').click()
    pg.wait_for_timeout(400)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _history(pg):
    return pg.evaluate("() => ({ action: window.app.history[window.app.historyIndex].action, index: window.app.historyIndex })")


def _select(pg, ids_, primary=None):
    pg.evaluate("(a) => window.app.setSelectedLayersByIds(a.ids, a.primary)",
                {'ids': ids_, 'primary': primary if primary is not None else ids_[0]})
    pg.wait_for_timeout(200)


def _open_from_row(pg, layer_id):
    pg.locator(f'#layers-list .layer-item[data-layer-id="{layer_id}"] .layer-cabinet-btn').click()
    pg.wait_for_timeout(300)
    return pg.evaluate(MODAL_JS)


def _wait_for_catalog(pg):
    pg.wait_for_selector('#panel-catalog-list .panel-catalog-row', timeout=15000)


def _pick_catalog_panel(pg, avoid_px):
    _wait_for_catalog(pg)
    return pg.evaluate(PICK_PANEL_JS, avoid_px)


def _confirm(pg):
    pg.locator('#preset-picker-add').click()
    pg.wait_for_timeout(900)


def _cancel(pg):
    pg.locator('#preset-picker-cancel').click()
    pg.wait_for_timeout(150)


def _close_menu(pg):
    pg.keyboard.press('Escape')
    pg.evaluate("() => window.app.hideContextMenu()")
    pg.wait_for_timeout(100)


def _expect_cabinet(fields, panel, unit='kg'):
    assert fields['cabinet_width'] == panel['pixels_w']
    assert fields['cabinet_height'] == panel['pixels_h']
    assert fields['panel_width_mm'] == panel['width_mm']
    assert fields['panel_height_mm'] == panel['height_mm']
    assert fields['panel_weight'] == panel['weight_kg']
    assert fields['weight_unit'] == unit
    assert fields['panelWatts'] == panel['watts_max']


def _expect_rest_kept(before, after):
    for k in ('name', 'columns', 'rows', 'offset_x', 'offset_y', 'group_id', 'flowPattern', 'panels'):
        assert after[k] == before[k], (k, before[k], after[k])


# ── the ways in ───────────────────────────────────────────────────────────

def test_the_row_button_opens_the_picker_in_replace_mode(page):
    pg, ids = page
    c, a = ids['c'], ids['a']
    # the button sits on every screen row, immediately left of the eye
    order = pg.evaluate("""(id) => {
        const row = document.querySelector(`#layers-list .layer-item[data-layer-id="${id}"]`);
        const btns = [...row.querySelectorAll('.layer-controls > button')].map(b => b.className);
        const cab = row.querySelector('.layer-cabinet-btn');
        return {btns, title: cab.title, eyeIsNext: cab.nextElementSibling.classList.contains('layer-visibility-btn')};
    }""", c)
    assert order['title'] == 'Change cabinet…' and order['eyeIsNext'], order
    # clicking it does not change the selection (A is selected, C's button is clicked)
    _select(pg, [a])
    st = _open_from_row(pg, c)
    assert st['shown'] and st['mode'] == 'replace', st
    assert st['title'] == 'Change cabinet for CENTER'
    assert st['confirm'] == 'Change' and st['targets'] == [c]
    assert 'Only the cabinet changes' in st['brief']
    assert pg.evaluate("() => [...window.app.selectedLayerIds]") == [a]
    _cancel(pg)
    assert not pg.evaluate(MODAL_JS)['shown']
    # + Add Screen opens the same modal with its own chrome back
    pg.evaluate("() => window.app.openPresetPicker()")
    pg.wait_for_timeout(200)
    st = pg.evaluate(MODAL_JS)
    assert st['mode'] == 'add' and st['title'] == 'Add Screen' and st['confirm'] == 'Add Screen'
    assert 'saved preset' in st['brief'] and st['targets'] == []
    _cancel(pg)
    # an image row and a text row carry no button
    has = pg.evaluate("""() => {
        const app = window.app;
        app.project.layers.push({id: 999001, type: 'image', name: 'PIC', visible: true,
            offset_x: 0, offset_y: 0, imageWidth: 10, imageHeight: 10, imageScale: 1, panels: []});
        app.project.layers.push({id: 999002, type: 'text', name: 'TXT', visible: true,
            offset_x: 0, offset_y: 0, textContent: 'hi', fontSize: 24, panels: []});
        app.renderLayers();
        const out = [999001, 999002].map(id => !!document.querySelector(
            `#layers-list .layer-item[data-layer-id="${id}"] .layer-cabinet-btn`));
        app.project.layers = app.project.layers.filter(l => l.id < 999000);
        app.renderLayers();
        return out;
    }""")
    assert has == [False, False]
    assert ids['errors'] == []


def test_the_menu_item_is_offered_for_screens_only(page):
    pg, ids = page
    a, c = ids['a'], ids['c']
    # a Screens panel row, right-clicked inside a two-screen selection
    _select(pg, [a, c])
    pg.locator(f'#layers-list .layer-item[data-layer-id="{c}"] .layer-header').click(button='right')
    pg.wait_for_timeout(300)
    st = pg.evaluate(MENU_JS)
    assert st['menuShown'] and st['shown'], st
    assert st['label'] == 'Change cabinet…' and st['selected'] == sorted([a, c])
    pg.locator('#context-menu [data-action="change-cabinet"]').click()
    pg.wait_for_timeout(300)
    assert not pg.evaluate(MENU_JS)['menuShown']
    st = pg.evaluate(MODAL_JS)
    assert st['shown'] and st['mode'] == 'replace', st
    assert st['title'] == 'Change cabinet for 2 screens' and st['targets'] == sorted([a, c])
    _cancel(pg)
    # the canvas, a real right-click on CENTER alone
    _select(pg, [c])
    pg.evaluate("(id) => { window.app.centerCanvasOnLayer(id); window.canvasRenderer.render(); }", c)
    pg.wait_for_timeout(150)
    pt = pg.evaluate(LAYER_POINT_JS, c)
    assert pt['inside'], pt
    pg.mouse.click(pt['x'], pt['y'], button='right')
    pg.wait_for_timeout(300)
    st = pg.evaluate(MENU_JS)
    assert st['menuShown'] and st['shown'] and st['selected'] == [c], st
    _close_menu(pg)
    # an image layer alone: the menu opens, the item is not on it
    pg.evaluate("""() => {
        const app = window.app;
        app.project.layers.push({id: 999001, type: 'image', name: 'PIC', visible: true,
            offset_x: 0, offset_y: 0, imageWidth: 10, imageHeight: 10, imageScale: 1, panels: []});
        app.setSelectedLayersByIds([999001], 999001);
    }""")
    pg.wait_for_timeout(200)
    pg.evaluate("(pt) => window.app.showContextMenu(pt.x, pt.y)", pt)
    st = pg.evaluate(MENU_JS)
    assert st['menuShown'] and not st['shown'], st
    _close_menu(pg)
    pg.evaluate("""(id) => {
        const app = window.app;
        app.project.layers = app.project.layers.filter(l => l.id !== 999001);
        app.selectLayer(app.project.layers.find(l => l.id === id));
    }""", c)
    pg.wait_for_timeout(200)
    assert ids['errors'] == []


# ── the write ─────────────────────────────────────────────────────────────

def test_one_screen_takes_the_new_cabinet_and_keeps_the_rest(page):
    pg, ids = page
    c = ids['c']
    _select(pg, [c])
    before = pg.evaluate(FIELDS_JS, c)
    assert before['cabinet_width'] == 128 and before['columns'] == 3 and before['rows'] == 5
    hist = _history(pg)
    st = _open_from_row(pg, c)
    assert st['title'] == 'Change cabinet for CENTER'
    panel = _pick_catalog_panel(pg, [128, 200])
    _confirm(pg)
    after = pg.evaluate(FIELDS_JS, c)
    _expect_cabinet(after, panel)
    _expect_rest_kept(before, after)
    # the server rebuilt the panels on the new cabinet and the echo landed them
    assert after['panel0'] == [panel['pixels_w'], panel['pixels_h']]
    served = pg.evaluate(SERVED_JS, c)
    _expect_cabinet(served, panel)
    _expect_rest_kept(before, served)
    # one entry for the change
    now = _history(pg)
    assert now['action'] == 'Change Cabinet' and now['index'] == hist['index'] + 1
    # the Screens row and the Screen Info panel read the new cabinet
    row = pg.evaluate("(id) => document.querySelector(`#layers-list .layer-item[data-layer-id=\"${id}\"] .layer-info`).textContent", c)
    assert f"{panel['pixels_w']}×{panel['pixels_h']}px" in row
    assert pg.evaluate("() => document.getElementById('cabinet-width').value") == str(panel['pixels_w'])
    assert pg.evaluate("() => document.getElementById('panel-width-mm').value") == str(panel['width_mm'])
    assert ids['errors'] == []


def test_two_selected_change_together_and_a_grouped_partner_does_not(page):
    pg, ids = page
    a, b, c = ids['a'], ids['b'], ids['c']
    _select(pg, [a, c], primary=a)
    before = {k: pg.evaluate(FIELDS_JS, k) for k in (a, b, c)}
    assert before[a]['group_id'] == 'g1' and before[b]['group_id'] == 'g1'
    hist = _history(pg)
    # the group's rows sit folded under its header; unfold to reach WALL-A's row
    pg.evaluate("() => window.app.setGroupExpanded('g1', true)")
    pg.wait_for_timeout(150)
    pg.locator(f'#layers-list .layer-item[data-layer-id="{a}"] .layer-header').click(button='right')
    pg.wait_for_timeout(300)
    pg.locator('#context-menu [data-action="change-cabinet"]').click()
    pg.wait_for_timeout(300)
    st = pg.evaluate(MODAL_JS)
    assert st['title'] == 'Change cabinet for 2 screens' and st['targets'] == sorted([a, c]), st
    panel = _pick_catalog_panel(pg, [128, 200, before[c]['cabinet_width']])
    _confirm(pg)
    after = {k: pg.evaluate(FIELDS_JS, k) for k in (a, b, c)}
    for k in (a, c):
        _expect_cabinet(after[k], panel)
        _expect_rest_kept(before[k], after[k])
        served = pg.evaluate(SERVED_JS, k)
        _expect_cabinet(served, panel)
    # WALL-B, A's group partner, is exactly as it was - on the client and the server
    assert after[b] == before[b]
    assert pg.evaluate(SERVED_JS, b) == before[b]
    # the group itself is untouched
    assert pg.evaluate("() => window.app.project.groups.map(g => [g.id, g.layer_ids])") == [['g1', [a, b]]]
    # ONE entry for both screens
    now = _history(pg)
    assert now['action'] == 'Change Cabinet' and now['index'] == hist['index'] + 1
    ids['undo'] = {'before': before, 'after': after, 'index': hist['index']}
    assert ids['errors'] == []


def test_undo_restores_every_changed_screen_and_redo_brings_the_cabinet_back(page):
    pg, ids = page
    a, b, c = ids['a'], ids['b'], ids['c']
    rec = ids['undo']
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(1200)
    for k in (a, b, c):
        assert pg.evaluate(FIELDS_JS, k) == rec['before'][k], k
        assert pg.evaluate(SERVED_JS, k) == rec['before'][k], k
    assert _history(pg)['index'] == rec['index']
    pg.evaluate("() => window.app.redo()")
    pg.wait_for_timeout(1200)
    for k in (a, c):
        got = pg.evaluate(FIELDS_JS, k)
        for f in ('cabinet_width', 'cabinet_height', 'panel_width_mm', 'panel_height_mm',
                  'panel_weight', 'weight_unit', 'panelWatts', 'columns', 'rows', 'name'):
            assert got[f] == rec['after'][k][f], (k, f)
    assert pg.evaluate(FIELDS_JS, b) == rec['before'][b]
    assert ids['errors'] == []


def test_a_saved_preset_lends_only_its_cabinet(page):
    pg, ids = page
    c = ids['c']
    name = 'E2E Change Cabinet'
    preset = {'name': 'NOT-CENTER', 'columns': 9, 'rows': 9, 'offset_x': 5000, 'offset_y': 5000,
              'cabinet_width': 176, 'cabinet_height': 176, 'panel_width_mm': 550,
              'panel_height_mm': 550, 'panel_weight': 12.5, 'weight_unit': 'lb',
              'panelWatts': 333, 'flowPattern': 'br-v', 'group_id': 'g1'}
    pg.evaluate("""async (a) => {
        await fetch('/api/presets/' + encodeURIComponent(a.name), {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({data: a.data})});
    }""", {'name': name, 'data': preset})
    try:
        _select(pg, [c])
        before = pg.evaluate(FIELDS_JS, c)
        hist = _history(pg)
        _open_from_row(pg, c)
        pg.wait_for_selector(f'#preset-picker-list .preset-picker-row[data-key="{name}"]', timeout=5000)
        pg.locator(f'#preset-picker-list .preset-picker-row[data-key="{name}"]').click()
        pg.wait_for_timeout(150)
        assert pg.evaluate("() => document.getElementById('preset-picker-summary').textContent") == f'Preset: {name}'
        _confirm(pg)
        after = pg.evaluate(FIELDS_JS, c)
        assert (after['cabinet_width'], after['cabinet_height']) == (176, 176)
        assert (after['panel_width_mm'], after['panel_height_mm']) == (550, 550)
        assert (after['panel_weight'], after['weight_unit'], after['panelWatts']) == (12.5, 'lb', 333)
        # the preset's columns, rows, name, offsets, pattern and group never landed
        _expect_rest_kept(before, after)
        assert after['group_id'] is None
        assert after['flowPattern'] == before['flowPattern'] and after['flowPattern'] != 'br-v'
        served = pg.evaluate(SERVED_JS, c)
        assert served['cabinet_width'] == 176 and served['columns'] == before['columns']
        assert served['name'] == 'CENTER' and served['offset_x'] == before['offset_x']
        now = _history(pg)
        assert now['action'] == 'Change Cabinet' and now['index'] == hist['index'] + 1
    finally:
        pg.evaluate("(n) => fetch('/api/presets/' + encodeURIComponent(n), {method: 'DELETE'})", name)
        pg.wait_for_timeout(200)
    assert ids['errors'] == []


def test_a_screen_sized_by_wall_dimensions_refits_its_grid(page):
    pg, ids = page
    c = ids['c']
    _select(pg, [c])
    # CENTER sized by px: 1280 x 640 on its current cabinet
    pg.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        l.sizeByDimensions = true; l.targetUnit = 'px'; l.targetWidth = 1280; l.targetHeight = 640;
        const fit = app.computeTilesForWall(l);
        l.columns = fit.columns; l.rows = fit.rows;
        app.updateLayers([l]);
        app.saveState('Update Properties');
    }""", c)
    pg.wait_for_timeout(600)
    before = pg.evaluate(FIELDS_JS, c)
    assert before['columns'] == round(1280 / before['cabinet_width'])
    _open_from_row(pg, c)
    panel = _pick_catalog_panel(pg, [128, 200, before['cabinet_width']])
    _confirm(pg)
    after = pg.evaluate(FIELDS_JS, c)
    _expect_cabinet(after, panel)
    assert after['columns'] == max(1, round(1280 / panel['pixels_w']))
    assert after['rows'] == max(1, round(640 / panel['pixels_h']))
    assert after['panels'] == after['columns'] * after['rows']
    served = pg.evaluate(SERVED_JS, c)
    assert (served['columns'], served['rows']) == (after['columns'], after['rows'])
    # the mode off again, so nothing after this reads a sized screen
    pg.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        l.sizeByDimensions = false;
        app.updateLayers([l]);
        app.saveState('Update Properties');
    }""", c)
    pg.wait_for_timeout(400)
    assert ids['errors'] == []
