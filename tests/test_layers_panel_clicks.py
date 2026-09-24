"""Screens panel: a click on a screen's NAME selects that screen.

The name field fills a row's header, so it is where most clicks on a row
land - and until 2026-09-23 the row's click handler skipped every click
whose target was the name (app-layers-panel.js), while the name itself
had no click handler. A single click on the name did nothing; only the
info line under it selected. The row comment always said "single-click
selects layer, double-click edits name".

Now the name behaves like the rest of the row for a click - plain click
selects, Cmd/Ctrl-click adds, Shift-click ranges - with two exclusions,
both about the rename. A name being EDITED: a double-click puts it in
edit mode, a further click inside it keeps the edit and the selection,
and Enter / Escape end it (Escape drops the typing, as the canvas name
field does). And the second click of a double-click: every select
rebuilds the list, and a rebuild on that click sends the dblclick to a
detached field, so the rename never opened (the probe that found it:
no dblclick reached the document at all).

Run locally (each session takes its own free port, so it runs beside
any other):
    python3 -m pytest tests/test_layers_panel_clicks.py -v --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

import app as app_module  # noqa: E402,F401

# Ctrl-click on macOS Chromium is a context-menu gesture, not a click, so
# the "add to selection" modifier is the platform's own.
MOD = 'Meta' if sys.platform == 'darwin' else 'Control'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the wiring (new files must not rot) ──────────────────────────────────

def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
        return fh.read()


def test_the_row_click_handler_only_skips_a_name_being_edited():
    rows = _src('src', 'static', 'js', 'app-layers-panel.js')
    assert "import './app-layers-panel.js';" in _src('src', 'static', 'js', 'main.js')
    assert "if (onName && (!e.target.readOnly || e.detail >= 2)) return;" in rows
    # The old blanket exclusion must not come back.
    assert "!e.target.classList.contains('layer-name-input')" not in rows
    assert "e.key === 'Escape' && !nameInput.readOnly" in rows


# ── the browser ───────────────────────────────────────────────────────────

# Three screens in one canvas. The list shows newest on top, so the rows
# read CHARLIE, BRAVO, ALPHA and a range from ALPHA to CHARLIE takes BRAVO.
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
    await add({name: 'ALPHA', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               offset_x: 0, offset_y: 0});
    await add({name: 'BRAVO', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               offset_x: 1000, offset_y: 0});
    await add({name: 'CHARLIE', columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
               offset_x: 2000, offset_y: 0});
    const p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('layers_panel_clicks_setup');
    const A = p.layers.find(l => l.name === 'ALPHA');
    const B = p.layers.find(l => l.name === 'BRAVO');
    const C = p.layers.find(l => l.name === 'CHARLIE');
    app.selectLayer(app.project.layers.find(l => l.id === C.id));
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Layers Panel Clicks Seed');
    return {a: A.id, b: B.id, c: C.id};
}"""

# The selection as the app holds it and as the list paints it.
SEL_JS = """() => {
    const app = window.app;
    const rows = [...document.querySelectorAll('#layers-list .layer-item')];
    return {
        current: app.currentLayer ? app.currentLayer.id : null,
        selected: [...(app.selectedLayerIds || [])].sort((x, y) => x - y),
        active: rows.filter(r => r.classList.contains('active')).map(r => +r.dataset.layerId).sort((x, y) => x - y),
        primary: rows.filter(r => r.classList.contains('primary')).map(r => +r.dataset.layerId),
    };
}"""

# One screen's name field: its edit state and whether it is the same
# element as before (a rebuild of the list would lose the probe mark).
NAME_JS = """(id) => {
    const el = document.querySelector(`#layers-list .layer-item[data-layer-id="${id}"] .layer-name-input`);
    if (!el) return null;
    return {
        readOnly: el.readOnly,
        editing: el.classList.contains('editing'),
        focused: document.activeElement === el,
        probe: el.dataset.probe || null,
        value: el.value,
    };
}"""

MARK_JS = """(id) => {
    const el = document.querySelector(`#layers-list .layer-item[data-layer-id="${id}"] .layer-name-input`);
    el.dataset.probe = 'same-element';
}"""

NAMES_JS = """async () => {
    const app = window.app;
    const p = await (await fetch('/api/project')).json();
    const pick = (layers) => Object.fromEntries(layers.map(l => [l.id, l.name]));
    return {app: pick(app.project.layers), server: pick(p.layers)};
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


def _name(pg, layer_id):
    return pg.locator(f'#layers-list .layer-item[data-layer-id="{layer_id}"] .layer-name-input')


def _click_name(pg, layer_id, **kw):
    _name(pg, layer_id).click(**kw)
    pg.wait_for_timeout(250)
    return pg.evaluate(SEL_JS)


def _end_any_edit(pg):
    pg.evaluate("""() => {
        const el = document.querySelector('#layers-list .layer-name-input.editing');
        if (el) el.blur();
    }""")
    pg.wait_for_timeout(150)


def test_a_click_on_the_name_selects_that_screen(page):
    pg, ids = page
    a, c = ids['a'], ids['c']
    before = pg.evaluate(SEL_JS)
    assert before['current'] == c, "the seed leaves CHARLIE current"

    got = _click_name(pg, a)
    assert got['current'] == a, f"a click on ALPHA's name did not make it current: {got}"
    assert got['selected'] == [a], got
    assert got['active'] == [a] and got['primary'] == [a], f"the list does not paint it: {got}"
    # And the name is still a read-only label, not an edit.
    nm = pg.evaluate(NAME_JS, a)
    assert nm['readOnly'] and not nm['editing'], f"a single click opened the rename: {nm}"


def test_a_click_on_the_info_line_still_selects(page):
    pg, ids = page
    a, b = ids['a'], ids['b']
    _click_name(pg, a)
    pg.locator(f'#layers-list .layer-item[data-layer-id="{b}"] .layer-info').click()
    pg.wait_for_timeout(250)
    got = pg.evaluate(SEL_JS)
    assert got['current'] == b and got['selected'] == [b], got


def test_cmd_click_on_a_second_name_adds_it(page):
    pg, ids = page
    a, c = ids['a'], ids['c']
    _click_name(pg, a)
    got = _click_name(pg, c, modifiers=[MOD])
    assert got['selected'] == sorted([a, c]), f"{MOD}-click on CHARLIE's name did not add it: {got}"
    assert got['current'] == c, got
    assert got['active'] == sorted([a, c]), got
    # The same gesture on a selected name takes it back out.
    got = _click_name(pg, c, modifiers=[MOD])
    assert got['selected'] == [a] and got['current'] == a, got


def test_shift_click_on_a_name_ranges_from_the_anchor(page):
    pg, ids = page
    a, b, c = ids['a'], ids['b'], ids['c']
    _click_name(pg, a)
    got = _click_name(pg, c, modifiers=['Shift'])
    assert got['selected'] == sorted([a, b, c]), f"Shift-click on CHARLIE's name did not range: {got}"
    assert got['current'] == c, got
    assert got['active'] == sorted([a, b, c]), got


def test_double_click_starts_the_rename_and_a_click_inside_keeps_it(page):
    pg, ids = page
    a, b = ids['a'], ids['b']
    _click_name(pg, a)
    _name(pg, b).dblclick()
    pg.wait_for_timeout(250)
    nm = pg.evaluate(NAME_JS, b)
    assert nm and not nm['readOnly'] and nm['editing'] and nm['focused'], \
        f"a double-click on BRAVO's name did not open the rename: {nm}"
    sel = pg.evaluate(SEL_JS)
    assert sel['current'] == b and sel['selected'] == [b], \
        f"the double-click's clicks did not select BRAVO: {sel}"

    # A click inside the editing name places the caret. It must neither
    # rebuild the list (the field would be a new element and the edit
    # gone) nor touch the selection.
    pg.evaluate(MARK_JS, b)
    _name(pg, b).click()
    pg.wait_for_timeout(250)
    nm = pg.evaluate(NAME_JS, b)
    assert nm['probe'] == 'same-element', "the click inside the edit rebuilt the list"
    assert not nm['readOnly'] and nm['editing'] and nm['focused'], f"the edit ended: {nm}"
    assert pg.evaluate(SEL_JS) == sel, "the click inside the edit changed the selection"
    _end_any_edit(pg)


def test_enter_ends_the_rename_with_the_typed_name(page):
    pg, ids = page
    b = ids['b']
    _name(pg, b).dblclick()
    pg.wait_for_timeout(250)
    assert pg.evaluate(NAME_JS, b)['editing']
    pg.keyboard.type('BRAVO-2')
    pg.keyboard.press('Enter')
    pg.wait_for_timeout(500)
    nm = pg.evaluate(NAME_JS, b)
    assert nm['readOnly'] and not nm['editing'], f"Enter did not end the rename: {nm}"
    assert nm['value'] == 'BRAVO-2', nm
    names = pg.evaluate(NAMES_JS)
    assert names['app'][str(b)] == 'BRAVO-2', names
    assert names['server'][str(b)] == 'BRAVO-2', f"the rename never reached the server: {names}"
    assert pg.evaluate(SEL_JS)['current'] == b


def test_escape_ends_the_rename_and_keeps_the_old_name(page):
    pg, ids = page
    b = ids['b']
    _name(pg, b).dblclick()
    pg.wait_for_timeout(250)
    assert pg.evaluate(NAME_JS, b)['editing']
    pg.keyboard.type('NOT-THIS')
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(500)
    nm = pg.evaluate(NAME_JS, b)
    assert nm['readOnly'] and not nm['editing'], f"Escape did not end the rename: {nm}"
    assert nm['value'] == 'BRAVO-2', f"Escape kept the typing: {nm}"
    names = pg.evaluate(NAMES_JS)
    assert names['app'][str(b)] == 'BRAVO-2' and names['server'][str(b)] == 'BRAVO-2', names


def test_a_click_on_another_name_ends_an_edit_and_selects_it(page):
    pg, ids = page
    a, b = ids['a'], ids['b']
    _name(pg, b).dblclick()
    pg.wait_for_timeout(250)
    assert pg.evaluate(NAME_JS, b)['editing']
    got = _click_name(pg, a)
    assert got['current'] == a and got['selected'] == [a], got
    nm = pg.evaluate(NAME_JS, b)
    assert nm['readOnly'] and not nm['editing'], f"BRAVO's edit survived a click elsewhere: {nm}"


def test_no_page_errors(page):
    pg, ids = page
    assert ids['errors'] == [], ids['errors']


def test_a_name_with_quotes_and_brackets_shows_whole_in_the_panel(page):
    """The Screens panel wrote the name raw into the field's value, so a
    name with a double quote was cut at the quote (2026-09-24)."""
    page = page[0] if isinstance(page, tuple) else page
    name = 'Stage "A" <left> & right'
    page.evaluate("""async (name) => {
        const app = window.app;
        const l = app.project.layers.find(x => (x.type || 'screen') === 'screen');
        l.name = name;
        await app._putLayer(l.id, { name });
        app.renderLayers();
    }""", name)
    page.wait_for_timeout(300)
    shown = page.evaluate("""() => [...document.querySelectorAll('.layer-name-input')]
        .map(i => i.value)""")
    assert name in shown, shown
