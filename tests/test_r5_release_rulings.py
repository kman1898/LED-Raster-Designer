"""The owner's round 5 answers on the release copy and the half tiles.

  * A typed panel weight carries to the half tiles ("Follow the typed
    weight"): with a saved library model, a half tile weighs the library's
    half/full ratio times the screen's full weight. With no library half,
    or no saved model, it stays 0.65 of the full cabinet.
  * The v1.5.4 notes, What's New and the guide say what the app does
    today, and the wording outside the copy guards (a toast, the Change
    cabinet brief, an undo label, the About line and a few tooltips) uses
    US spelling, colons and commas, never a dash.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_r5_release_rulings.py -v --browser chromium
"""

import os
import re

import pytest

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, '..')
JS = os.path.join(ROOT, 'src', 'static', 'js')
VERSION_TXT = os.path.join(ROOT, 'src', 'VERSION.txt')
INDEX_HTML = os.path.join(ROOT, 'src', 'templates', 'index.html')


def _read(*parts):
    with open(os.path.join(*parts), encoding='utf-8') as f:
        return f.read()


def _top_entry():
    text = _read(VERSION_TXT)
    starts = [m.start() for m in re.finditer(r'^v\d[\w.]* - ', text, re.M)]
    return text[starts[0]:starts[1]]


def _flat(text):
    return re.sub(r'\s+', ' ', text)


# ── the v1.6.0 notes (written as 1.5.4) ──────────────────────────────────

def test_the_notes_say_what_160_does():
    top = _top_entry()
    assert top.startswith('v1.6.0 - ')
    flat = _flat(top)
    # the fix to code new in this release is gone; the refusal is one sentence of
    # the 80% section
    assert "doesn't repack a locked screen" not in flat
    assert ('A change that would repack a locked screen is refused, and the message names '
            'the screen: turning 100% rated on or off, changing a distro\'s system, removing a '
            'distro, plugging in, moving or unplugging a multi, grouping, sharing circuits '
            'through a 2fer or 3fer or removing one, 2fer it or 3fer it, typing a power '
            'setting on a screen grouped with it, or hiding or showing a screen.') in flat
    # lengths convert in every field but a jumper's
    assert 'converts wherever you type a home run, cable, power in, snake or fiber length' in flat
    assert 'converts wherever you type a cable length' not in flat
    # the readout always names the breaker, at 100% too
    assert '20 A breaker · 20 A usable where the breakers are 100% rated' in flat
    assert 'or 20 A usable' not in flat
    assert '16 A breaker · 12.8 A usable' in flat
    # wording
    assert 'A 400 A cam input lists a 400 A cam set' in flat
    assert "can't move a distro to another system while it's powered thru, or powers, another distro" in flat
    assert 'the GP2.6 Right Angle corners' in flat
    assert 'a data path you draw steps over them in the drawing too, the same as automatic routing' in flat
    # suffixes count distros that print; a typed weight reaches the halves
    assert 'Only distros that print are counted' in flat
    assert 'If you type your own panel weight, the half tiles follow it' in flat


def test_count_changes_are_listed_under_opening_an_older_show():
    top = _top_entry()
    older = top[top.index('OPENING AN OLDER SHOW'):top.index('\nFIXES\n')]
    flat = _flat(older)
    for line in ('- CHANGE (IMPORTANT): The pull sheet has a row for each panel type on each screen and a '
                 'Power in row for each distro',
                 '- CHANGE (IMPORTANT): Hidden screens keep their multi numbers and outputs reserved',
                 '- CHANGE (IMPORTANT): The Overview\'s totals in the binder leave out hidden screens.',
                 '- CHANGE (IMPORTANT): A distro with nothing on it, or only hidden screens, is left '
                 'off the binder, and a service with nothing printing on it gets no Service sheet.'):
        assert line in flat, line
    assert 'the last six change what\'s listed or what you can do' in flat


def test_whats_new_80_item_covers_a_screen_on_no_distro():
    src = _read(JS, 'whatsnew_content.js')
    entry = src[src.index("'1.6': {"):src.index("'1.5.3': {")]
    assert len(re.findall(r'\{\s*h:', entry)) == 8
    assert 'or on a screen with no distro at 208 V or below, is now filled to 80%' in entry
    assert 'A 400 A cam input lists a 400 A cam set' in entry


# ── the guide ─────────────────────────────────────────────────────────────

def test_the_guide_points_at_the_usable_amps():
    src = _read(JS, 'quickstart.js')
    step = src[src.index('panelWatts: {'):src.index('panelInput: {')]
    assert "'#power-amperage-usable'" in step
    assert 'Beside Amperage you see the amps you can use' in step
    assert "$('#power-amperage-usable')" in step
    share = src[src.index('splitters: {'):src.index('takeOver: {')]
    assert "' A usable on a '" in share and "' A breaker.'" in share
    assert "' A circuit.'" not in share


# ── wording outside the guards ────────────────────────────────────────────

def test_wording_outside_the_guards():
    export = _read(JS, 'app-export-io.js')
    assert export.count("'Export canceled, nothing was saved.'") == 2
    assert 'Export cancelled' not in export
    presets = _read(JS, 'app-presets.js')
    assert 'Only the cabinet changes: pixels, millimeters, weight, watts.' in presets
    wiring = _read(JS, 'app-wiring.js')
    assert "'Toggle Data Tags'" in wiring and 'Toggle Data Cable Tags' not in wiring
    html = _read(INDEX_HTML)
    assert 'LED Raster Designer License: see Help > License.</div>' in html
    for text in ('Ports fill complete rows or columns: clean rectangular port regions. A row or column too long for one port is cut into ports of whole cabinets',
                 'Ports fill to maximum pixel capacity, and may split mid-row/column',
                 'Black and white: gray cabinets,',
                 'The power system a new distro starts on: the same list its gear offers.',
                 'Each follows its own map: Maps on Power gives no Data Wiring sheet',
                 'Elements puts each screen in a group of layers: Panels, Borders, Test pattern, '
                 'Cabinet IDs, Data, Power and Screen name. The images'):
        assert text in html, text
    assert 'grey cabinets' not in html and 'License — Help' not in html


# ── a typed weight carries to the half tiles ──────────────────────────────

pytest_playwright = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser, server_project_guard):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1000)
    yield pg, errors
    context.close()


# ROE Black Quartz 3.9 Full Tile, picked from the library: 22 kg, its
# Half Tile (halved in height) 9.8 kg; the library has no half halved in
# width. The last row is half tiles in height, one cabinet a half in
# width.
PICK_JS = """async () => {
    const app = window.app;
    await app._ensurePanelCatalogData();
    const panel = app._panelCatalog.ROE.find(p => p.name === 'Black Quartz 3.9 Full Tile');
    const before = app.project.layers.length;
    app.addLayer(app._pickedPanelPresetData({ ...panel, _mfr: 'ROE' }));
    for (let i = 0; i < 100 && app.project.layers.length === before; i++) await new Promise(r => setTimeout(r, 50));
    await new Promise(r => setTimeout(r, 400));
    const id = app.project.layers[app.project.layers.length - 1].id;
    const layer = () => app.project.layers.find(x => x.id === id);
    app.selectLayer(layer());
    const last = Math.max(...layer().panels.map(p => p.row));
    await app.setPanelsHalfTileBulk(layer().panels.filter(p => p.row === last), 'height');
    await app.setPanelsHalfTileBulk([layer().panels.find(p => p.row === 0 && p.col === 0)], 'width');
    await new Promise(r => setTimeout(r, 400));
    return id;
}"""

WEIGHT_JS = """async ([id, value]) => {
    const app = window.app;
    const l = app.project.layers.find(x => x.id === id);
    if (value !== null) {
        app.selectLayer(l);
        app.loadLayerToInputs();
        const el = document.getElementById('panel-weight-kg');
        el.value = value;
        el.dispatchEvent(new Event('change'));
        await new Promise(r => setTimeout(r, 500));
    }
    const last = Math.max(...l.panels.map(p => p.row));
    const half = l.panels.find(p => p.row === last && p.halfTile === 'height');
    const side = l.panels.find(p => p.halfTile === 'width');
    const full = l.panels.find(p => !p.halfTile || p.halfTile === 'none');
    return { id: l.panelModelId ?? null, unit: l.weight_unit || 'kg', weight: Number(l.panel_weight),
             full: app.getPanelWeightKg(l, full), half: app.getPanelWeightKg(l, half),
             side: app.getPanelWeightKg(l, side) };
}"""


@pytest.fixture(scope="module")
def quartz(page):
    return page[0].evaluate(PICK_JS)


def test_a_typed_weight_carries_to_the_half_tiles(page, quartz):
    pg, errors = page
    qid = quartz
    got = pg.evaluate(WEIGHT_JS, [qid, None])
    assert got['id'] == 'ROE|Black Quartz 3.9 Full Tile' and got['unit'] == 'kg', got
    # as picked: the library's own half
    assert (got['full'], got['half']) == (22, 9.8), got
    assert abs(got['side'] - 0.65 * 22) < 1e-9, got
    # type 30 kg: the half follows, 9.8 / 22 of it; the width half (no
    # library half) stays 0.65 of the full cabinet
    got = pg.evaluate(WEIGHT_JS, [qid, '30'])
    assert got['id'] == 'ROE|Black Quartz 3.9 Full Tile' and got['weight'] == 30, got
    assert got['full'] == 30, got
    assert abs(got['half'] - 9.8 / 22 * 30) < 1e-9, got
    assert abs(got['side'] - 0.65 * 30) < 1e-9, got
    # back at the library's 22 kg, the half is the library's own again
    got = pg.evaluate(WEIGHT_JS, [qid, '22'])
    assert (got['full'], got['half']) == (22, 9.8), got
    assert not errors, errors


def test_without_a_saved_model_a_typed_weight_keeps_065(page, quartz):
    """A show saved before 1.5.4 has no model on its screens: its cabinet
    is found by size, pixels and weight, so a typed weight finds nothing
    and the half is 0.65 of the full cabinet."""
    pg, _ = page
    got = pg.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        const old = { ...l, panelModelId: null, panelModelName: null, panelModelHalves: null,
                      panel_weight: 30 };
        const half = l.panels.find(p => p.halfTile === 'height');
        return { lib: app.catalogHalfWeightKg({ ...old, panel_weight: 22 }, 'height'),
                 typed: app.catalogHalfWeightKg(old, 'height'), kg: app.getPanelWeightKg(old, half) };
    }""", quartz)
    assert got['lib'] == 9.8, got
    assert got['typed'] is None and abs(got['kg'] - 0.65 * 30) < 1e-9, got
