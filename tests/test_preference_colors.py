"""Issue 28: the colour defaults for a new screen, read from the sources
and driven in the browser.

Every colour picker the Preferences dialog gained (Look: info labels and
cabinet ID text; Data: line, arrow, primary and backup port; Power: line,
arrow, circuit label, circuits A to F) is one id in index.html, one key in
getPreferencesDefaults, one setColor in fillPreferencesUI, one readColor
in readPreferencesFromUI, and one read in initializeLayerDefaults (or, for
the two the server sets, in addLayer's request). A picker that misses any
of those is a swatch that does nothing; the source tests say which.

The browser tests cover what the exploratory pass after the feature found:
a new screen's colours reaching the server (so they survive a reload), an
existing screen's circuit colours NOT following the preference, the
pristine startup screen taking the colour defaults on Save, a malformed
stored preference not turning black, paste carrying the Data colours the
way duplicate does, and a preset with empty colour keys taking the default.

The dialog round trip (set, Save, add a screen) is in test_preferences.

Run locally:
    python3 -m pytest tests/test_preference_colors.py -v --browser chromium
"""
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, 'src', 'templates', 'index.html')
PREFS_JS = os.path.join(ROOT, 'src', 'static', 'js', 'app-preferences.js')
PRESETS_JS = os.path.join(ROOT, 'src', 'static', 'js', 'app-presets.js')
CORE_JS = os.path.join(ROOT, 'src', 'static', 'js', 'app-core.js')
NAMING_JS = os.path.join(ROOT, 'src', 'static', 'js', 'app-naming.js')
CANVAS_LABELS_JS = os.path.join(ROOT, 'src', 'static', 'js', 'canvas-labels.js')

# picker id -> (preference key, shipped default, where the new screen reads it)
PICKERS = {
    'pref-screen-name-color': ('screenNameColor', '#FFFFFF', 'addLayer'),
    'pref-cabinet-id-color': ('cabinetIdColor', '#FFFFFF', 'addLayer'),
    'pref-data-line-color': ('dataLineColor', '#FFFFFF', 'dataFlowColor'),
    'pref-data-arrow-color': ('dataArrowColor', '#0042AA', 'arrowColor'),
    'pref-data-primary-color': ('dataPrimaryColor', '#00FF00', 'primaryColor'),
    'pref-data-primary-text-color': ('dataPrimaryTextColor', '#000000', 'primaryTextColor'),
    'pref-data-backup-color': ('dataBackupColor', '#FF0000', 'backupColor'),
    'pref-data-backup-text-color': ('dataBackupTextColor', '#FFFFFF', 'backupTextColor'),
    'pref-power-line-color': ('powerLineColor', '#FF0000', 'powerLineColor'),
    'pref-power-arrow-color': ('powerArrowColor', '#0042AA', 'powerArrowColor'),
    'pref-power-label-bg-color': ('powerLabelBgColor', '#D95000', 'powerLabelBgColor'),
    'pref-power-label-text-color': ('powerLabelTextColor', '#000000', 'powerLabelTextColor'),
}
CIRCUIT_IDS = [f'pref-power-circuit-color-{l}' for l in 'abcdef']
SHIPPED_CIRCUIT_COLORS = ['#BC382F', '#CC6B30', '#D2E94D', '#2CF82B', '#2145DC', '#7414F5']

# layer property -> preference key, for the twelve single colours
LAYER_OF = {
    'labelsColor': 'screenNameColor',
    'cabinetIdColor': 'cabinetIdColor',
    'dataFlowColor': 'dataLineColor',
    'arrowColor': 'dataArrowColor',
    'primaryColor': 'dataPrimaryColor',
    'primaryTextColor': 'dataPrimaryTextColor',
    'backupColor': 'dataBackupColor',
    'backupTextColor': 'dataBackupTextColor',
    'powerLineColor': 'powerLineColor',
    'powerArrowColor': 'powerArrowColor',
    'powerLabelBgColor': 'powerLabelBgColor',
    'powerLabelTextColor': 'powerLabelTextColor',
}
# A set of colours no shipped default shares, upper case the way a saved
# preference (and a layer) stores them.
COLOURS = {
    'screenNameColor': '#112233', 'cabinetIdColor': '#223344',
    'dataLineColor': '#334455', 'dataArrowColor': '#445566',
    'dataPrimaryColor': '#556677', 'dataPrimaryTextColor': '#667788',
    'dataBackupColor': '#778899', 'dataBackupTextColor': '#8899AA',
    'powerLineColor': '#99AABB', 'powerArrowColor': '#AABBCC',
    'powerLabelBgColor': '#BBCCDD', 'powerLabelTextColor': '#CCDDEE',
    'powerCircuitColors': ['#A10001', '#A20002', '#A30003', '#A40004', '#A50005', '#A60006'],
}
COLOURS_AS_LAYER = {prop: COLOURS[key] for prop, key in LAYER_OF.items()}
COLOURS_AS_LAYER['powerCircuitColors'] = dict(zip('ABCDEF', COLOURS['powerCircuitColors']))


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _section(html, key):
    m = re.search(r'<section class="pm-section" id="pm-sec-%s".*?</section>' % key, html, re.S)
    assert m, key
    return m.group(0)


# ── the sources ───────────────────────────────────────────────────────────

def test_every_colour_picker_is_in_the_dialog_once_on_its_own_tab():
    html = _read(INDEX_HTML)
    tabs = {'look': ['pref-color1', 'pref-color2', 'pref-border-color',
                     'pref-screen-name-color', 'pref-cabinet-id-color'],
            'data': [i for i in PICKERS if i.startswith('pref-data-')],
            'power': [i for i in PICKERS if i.startswith('pref-power-')] + CIRCUIT_IDS}
    for key, ids in tabs.items():
        sec = _section(html, key)
        for pid in ids:
            assert html.count(f'id="{pid}"') == 1, pid
            assert f'<input type="color" id="{pid}"' in sec, (key, pid)
        # the note that says what the pickers are for, once per tab
        assert sec.count('Used for new screens. Change a screen\'s own colors on the Screen Info panel.') == 1, key
    # the three pickers that were one unlabelled row are now named
    look = _section(html, 'look')
    for label in ('Tile colors', 'Cabinet border', 'Info labels', 'Cabinet ID text'):
        assert f'<label>{label}</label>' in look, label
    assert '<label>Colors</label>' not in look
    assert '<label>Labels</label>' not in look


def test_the_info_label_picker_says_what_it_colours():
    """labelsColor colours the Pixel Map size / weight lines and the Data
    view's port-load plate - never the screen name, which canvas-labels
    draws black on a white plate on purpose. The row, its aria-label and
    its note say so; nothing in the dialog or the defaults calls it the
    screen name colour."""
    look = _section(_read(INDEX_HTML), 'look')
    row = look[look.index('<label>Info labels</label>'):look.index('<label>Cabinet ID text</label>')]
    assert 'id="pref-screen-name-color"' in row
    assert 'aria-label="Info label color: size, weight and port-load text"' in row
    assert 'title="Size, weight and port-load text. The screen name plate is fixed: black on white."' in row
    # beside the picker, not a note line: the Look tab's body has no room for one
    assert '<span>size, weight and port-load text; the screen name plate is fixed</span>' in row
    assert 'pm-note' not in row
    assert 'Screen name color' not in _read(INDEX_HTML)
    js = _read(PREFS_JS)
    defaults = js[js.index('getPreferencesDefaults() {'):js.index('getLocalPreferences() {')]
    assert 'the two the server sets: the info labels and' in defaults
    assert 'the two the server sets: the screen name' not in defaults
    assert 'It\n            // does NOT colour the screen name' in defaults
    # the reason: the name is drawn black on a white plate, whatever labelsColor is
    labels = _read(CANVAS_LABELS_JS)
    name = labels[labels.index('// Draw WHITE background'):labels.index('// Reset font for other labels')]
    assert "this.ctx.fillStyle = '#000000';" in name
    assert 'labelsColor' not in name


def test_every_colour_picker_has_a_default_a_load_and_a_save():
    js = _read(PREFS_JS)
    defaults = js[js.index('getPreferencesDefaults() {'):js.index('getLocalPreferences() {')]
    fill = js[js.index('fillPreferencesUI(prefs) {'):js.index('readPreferencesFromUI() {')]
    read = js[js.index('readPreferencesFromUI() {'):js.index('_webSafeFonts() {')]
    for pid, (key, shipped, _where) in PICKERS.items():
        assert re.search(r'^\s+%s: \'%s\',' % (key, shipped), defaults, re.M), (key, shipped)
        assert f"setColor('{pid}', '{key}');" in fill, pid
        assert f"{key}: readColor('{pid}', defaults.{key})," in read, pid
    # a stored value that is not a colour shows the shipped default, not black
    assert 'const setColor = (id, key) => setVal(id, this.normalizeHexColor(prefs[key], defaults[key]));' in fill
    assert 'powerCircuitColors: SHIPPED_CIRCUIT_COLORS.slice(),' in defaults
    assert "const SHIPPED_CIRCUIT_COLORS = ['%s'];" % "', '".join(SHIPPED_CIRCUIT_COLORS) in js
    assert "['a', 'b', 'c', 'd', 'e', 'f'].map(l => `pref-power-circuit-color-${l}`)" in js
    assert 'this._circuitColorPrefIds().forEach((id, i) => setVal(id, circuitColors[i]));' in fill
    assert 'powerCircuitColors: this._circuitColorPrefIds().map((id, i) => readColor(id, defaults.powerCircuitColors[i])),' in read
    # a saved colour is stored the way a layer stores it
    assert 'return el && el.value ? this.normalizeHexColor(el.value, fallback) : fallback;' in read


def test_a_new_screen_reads_every_colour_preference():
    presets = _read(PRESETS_JS)
    init = presets[presets.index('initializeLayerDefaults(layer) {'):]
    init = init[:init.index('layer.border_color_pixel')]
    core = _read(CORE_JS)
    add = core[core.index('addLayer(presetData) {'):core.index("fetch('/api/layer/add'")]
    for pid, (key, shipped, where) in PICKERS.items():
        if where == 'addLayer':
            # the server sets these two on create_layer; the request carries
            # the preference, checked - a malformed stored value never lands raw
            prop = {'screenNameColor': 'labelsColor', 'cabinetIdColor': 'cabinetIdColor'}[key]
            assert f"const {prop} = color(prefs.{key}, '{shipped}');" in add, (pid, prop)
            # the plain branch sends the checked preference; the preset branch
            # checks the preset's value with the preference behind it (a
            # preset 'nope' or 'red' is no colour: item 3 of the re-test)
            assert f"{prop}: {prop}" in add, (pid, prop)
            assert f"{prop}: color(presetData.{prop}, {prop})" in add, (pid, prop)
            assert f"presetData.{prop} ||" not in add, f'{prop}: a junk preset colour must not pass on ||'
            assert f'prefs.{key}' not in init, f'{key} is the server\'s to set'
        else:
            assert f"layer.{where} = color(prefs.{key}, '{shipped}');" in init, (pid, where)
    assert 'const color = (value, fallback) => this.normalizeHexColor(value, fallback);' in add
    assert 'layer.powerCircuitColors = this.getDefaultPowerCircuitColors();' in init
    naming = _read(NAMING_JS)
    fn = naming[naming.index('getDefaultPowerCircuitColors() {'):naming.index('normalizeHexColor(value')]
    assert 'const list = this.getPreferenceCircuitColorList();' in fn
    assert 'return { A: list[0], B: list[1], C: list[2], D: list[3], E: list[4], F: list[5] };' in fn
    for colour in SHIPPED_CIRCUIT_COLORS:
        assert colour not in fn, 'the shipped circuit colours live in app-preferences now'


def test_a_new_screen_is_pushed_to_the_server_preset_or_not():
    """create_layer stores literal defaults; every client-side default
    lives only in the browser until the PUT that follows the add. That PUT
    used to run only for a preset."""
    core = _read(CORE_JS)
    add = core[core.index('addLayer(presetData) {'):core.index('applyNewScreenPowerPreferences(layer, presetData) {')]
    assert 'this.updateLayers([layer]);' in add
    assert 'if (appliedPreset) {\n                this.updateLayers([layer]);' not in add


def test_an_existing_screen_fills_missing_circuit_colours_from_the_shipped_set():
    """normalizePowerCircuitColors runs on every load over every screen:
    it must read the SHIPPED colours, not the preference, or changing the
    preference repaints circuits on screens that already exist."""
    naming = _read(NAMING_JS)
    fn = naming[naming.index('normalizePowerCircuitColors(colors, project = this.project) {'):naming.index('getPowerCircuitLetter(circuitNum) {')]
    assert 'const shipped = this.getShippedCircuitColorList();' in fn
    assert 'this.getDefaultPowerCircuitColors()' not in fn
    # the fill reads the shipped set; the preference is read exactly once,
    # for the old-green guard (a chosen old green stays), never to fill
    assert 'next[letter] = this.normalizeHexColor(colors[letter], defaults[letter]);' in fn
    assert fn.count('this.getPreferenceCircuitColorList(') == 1
    assert 'const chosenD = this.getPreferenceCircuitColorList()[3] === oldShipped.D;' in fn
    js = _read(PREFS_JS)
    assert 'getShippedCircuitColorList() {\n        return SHIPPED_CIRCUIT_COLORS.slice();' in js


# ── the browser ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _guard(server_project_guard):
    """Leave the shared server project and its preferences the way this
    module found them: every test here writes a preference, adds screens,
    and the last one replaces the project outright. Not autouse - the
    source tests above need no server - so `page` asks for it first,
    which still puts its restore AFTER context.close()."""


@pytest.fixture(scope="module")
def page(_guard, e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e) + '\n' + str(getattr(e, 'stack', ''))))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg, errors
    context.close()


# Store a preference patch the way the dialog's Save does: the live copy,
# localStorage, and the server.
SET_PREFS_JS = """async (patch) => {
    const app = window.app;
    const prefs = { ...app.getPreferences(), ...patch };
    app._serverPreferences = prefs;
    try { localStorage.setItem('appPreferences', JSON.stringify(prefs)); } catch (e) {}
    await fetch('/api/preferences', { method: 'PUT',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(prefs) });
    return prefs;
}"""

# The one layer added since `before`, from the SERVER (a reload reads this).
SERVER_NEW_JS = """async (before) => {
    const p = await (await fetch('/api/project')).json();
    const fresh = p.layers.filter(l => !before.includes(l.id));
    return fresh.length === 1 ? fresh[0] : { error: `${fresh.length} new layers` };
}"""

# The one layer added since `before`, from the browser.
CLIENT_NEW_JS = """(before) => {
    const fresh = window.app.project.layers.filter(l => !before.includes(l.id));
    return fresh.length === 1 ? fresh[0] : { error: `${fresh.length} new layers` };
}"""

IDS_JS = "() => window.app.project.layers.map(l => l.id)"


def _colours_of(layer):
    got = {prop: (layer.get(prop) or '').upper() for prop in LAYER_OF}
    got['powerCircuitColors'] = layer.get('powerCircuitColors')
    return got


def _delete(pg, layer_id):
    pg.evaluate("(id) => window.app.deleteLayer(id)", layer_id)
    pg.wait_for_timeout(800)
    pg.evaluate("() => { const app = window.app; app.selectLayer(app.project.layers[0]); }")


def test_a_new_screen_keeps_its_preference_colours_on_reload(page):
    """Defect 1: addLayer applied the Preferences colours in the browser
    and pushed the layer to the server only for a preset, so the server
    held create_layer's literals and a reload (or any re-fetch) put the
    shipped colours back. The server's copy carries them now, and so does
    the page after a reload."""
    pg, errors = page
    pg.evaluate(SET_PREFS_JS, COLOURS)
    before = pg.evaluate(IDS_JS)
    pg.evaluate("() => window.app.addLayer()")
    pg.wait_for_timeout(1500)
    srv = pg.evaluate(SERVER_NEW_JS, before)
    assert 'error' not in srv, srv
    assert _colours_of(srv) == COLOURS_AS_LAYER, 'the server holds the literals, not the preference'
    # the other client-side defaults ride the same PUT
    assert srv['flowPattern'] == 'tl-h' and srv['bitDepth'] == 8 and srv['frameRate'] == 60, srv
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    live = pg.evaluate(CLIENT_NEW_JS, before)
    assert 'error' not in live, live
    assert _colours_of(live) == COLOURS_AS_LAYER, 'the reload lost the colours'
    _delete(pg, srv['id'])
    assert errors == [], errors


def test_an_existing_screen_does_not_follow_the_circuit_colour_preference(page):
    """Defect 3: the preference's circuit colours are for a NEW screen. A
    screen that exists fills a letter it lacks and an entry that is not a
    colour from the shipped set. (An old default green in D on a map that
    differs anywhere else is a chosen colour and stays: see the old-green
    test below.)"""
    pg, errors = page
    pg.evaluate(SET_PREFS_JS, {'powerCircuitColors': COLOURS['powerCircuitColors']})
    got = pg.evaluate("""() => {
        const app = window.app;
        return {
            fresh: app.getDefaultPowerCircuitColors(),
            partial: app.normalizePowerCircuitColors({ A: '#111111', C: 'nope', D: '#79FC4C' }),
            none: app.normalizePowerCircuitColors(undefined),
        };
    }""")
    shipped = dict(zip('ABCDEF', SHIPPED_CIRCUIT_COLORS))
    assert got['fresh'] == COLOURS_AS_LAYER['powerCircuitColors'], got['fresh']
    assert got['none'] == shipped, got['none']
    assert got['partial'] == dict(shipped, A='#111111', D='#79FC4C'), got['partial']
    # the seeded screen, loaded with no circuit colours of its own, has the shipped set
    first = pg.evaluate("() => window.app.project.layers[0].powerCircuitColors")
    assert first == shipped, first
    assert errors == [], errors


def test_a_malformed_stored_colour_shows_and_saves_the_shipped_default(page):
    """Defect 5: a colour input handed '#12345' or 'abcdef' shows black,
    and a Save with no edit then stored that black. The dialog shows the
    checked colour instead, Save stores it, and addLayer sends the
    checked colour to the server whatever the stored preference holds."""
    pg, errors = page
    pg.evaluate(SET_PREFS_JS, {'screenNameColor': '#12345', 'cabinetIdColor': 'abcdef',
                               'dataLineColor': 'not a colour'})
    before = pg.evaluate(IDS_JS)
    pg.evaluate("() => window.app.addLayer()")
    pg.wait_for_timeout(1500)
    srv = pg.evaluate(SERVER_NEW_JS, before)
    assert 'error' not in srv, srv
    assert (srv['labelsColor'], srv['cabinetIdColor']) == ('#FFFFFF', '#ABCDEF'), srv
    _delete(pg, srv['id'])
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_timeout(300)
    shown = pg.evaluate("""(ids) => ids.map(id => document.getElementById(id).value)""",
                        ['pref-screen-name-color', 'pref-cabinet-id-color', 'pref-data-line-color'])
    assert shown == ['#ffffff', '#abcdef', '#ffffff'], shown
    pg.locator('#preferences-save').click()
    pg.wait_for_timeout(600)
    served = pg.evaluate("async () => (await (await fetch('/api/preferences')).json())")
    assert (served['screenNameColor'], served['cabinetIdColor'], served['dataLineColor']) == \
        ('#FFFFFF', '#ABCDEF', '#FFFFFF'), served
    assert errors == [], errors


DATA_COLOURS = {
    'arrowColor': '#0A0B0C', 'dataFlowColor': '#0D0E0F',
    'primaryColor': '#1A1B1C', 'primaryTextColor': '#1D1E1F',
    'backupColor': '#2A2B2C', 'backupTextColor': '#2D2E2F',
}
# The add route takes every one of these (dataFlowColor joined the list on
# 2026-09-22; a pasted screen's data line used to land as the literal).
DATA_COLOURS_ON_SERVER = dict(DATA_COLOURS)


def _dress_and_copy(pg, how):
    state = pg.evaluate("""(colours) => {
        const app = window.app;
        const l = app.project.layers[0];
        Object.assign(l, colours);
        app.updateLayers([l]);
        return { sourceId: l.id, before: app.project.layers.map(x => x.id) };
    }""", DATA_COLOURS)
    pg.wait_for_timeout(700)
    if how == 'paste':
        pg.evaluate("""(id) => {
            const app = window.app;
            app.currentLayer = app.project.layers.find(x => x.id === id);
            app.copyLayer();
            app.pasteLayer();
        }""", state['sourceId'])
    else:
        pg.evaluate("""(id) => {
            const l = window.app.project.layers.find(x => x.id === id);
            window.app.duplicateLayer(l);
        }""", state['sourceId'])
    pg.wait_for_timeout(1200)
    return state


@pytest.mark.parametrize('how', ['paste', 'duplicate'])
def test_a_copy_carries_the_data_colours(page, how):
    """Defect 6: paste sent none of the Data tab's colours and stamped only
    the two text colours afterwards, so a pasted screen came out with the
    shipped line, arrow and port colours. Duplicate stamped all six in the
    browser and sent none. Both now carry the set, in the browser and to
    the server."""
    pg, errors = page
    state = _dress_and_copy(pg, how)
    live = pg.evaluate(CLIENT_NEW_JS, state['before'])
    assert 'error' not in live, (how, live)
    assert {k: live.get(k) for k in DATA_COLOURS} == DATA_COLOURS, f'{how} lost a Data colour in the browser'
    srv = pg.evaluate(SERVER_NEW_JS, state['before'])
    assert {k: srv.get(k) for k in DATA_COLOURS_ON_SERVER} == DATA_COLOURS_ON_SERVER, \
        f'{how} reached the server without its Data colours'
    _delete(pg, live['id'])
    assert errors == [], errors


def test_a_preset_with_empty_colour_keys_takes_the_defaults(page):
    """Defect 7: a preset carrying a colour as null or '' landed it raw on
    the new screen. Those keys are skipped, so the Preferences default the
    screen was given stays."""
    pg, errors = page
    pg.evaluate(SET_PREFS_JS, COLOURS)
    before = pg.evaluate(IDS_JS)
    pg.evaluate("""() => window.app.addLayer({
        columns: 2, rows: 2, _presetName: 'empty colours',
        labelsColor: null, cabinetIdColor: '',
        arrowColor: null, dataFlowColor: '', primaryColor: null, backupTextColor: '',
        powerLineColor: '', powerLabelBgColor: null,
        powerCircuitColors: null, border_color_data: null,
        bitDepth: 10,
    })""")
    pg.wait_for_timeout(1500)
    live = pg.evaluate(CLIENT_NEW_JS, before)
    assert 'error' not in live, live
    assert _colours_of(live) == COLOURS_AS_LAYER, live
    assert (live['border_color_data'] or '').upper() == '#FFFFFF', live['border_color_data']
    assert live['bitDepth'] == 10 and live['columns'] == 2, 'the rest of the preset still applies'
    srv = pg.evaluate(SERVER_NEW_JS, before)
    assert _colours_of(srv) == COLOURS_AS_LAYER, srv
    _delete(pg, live['id'])
    assert errors == [], errors


def test_the_pristine_startup_screen_takes_the_colour_defaults_on_save(page):
    """Defect 4: on the untouched startup project, Save in Preferences
    re-made the one screen from the preferences - tile colours included -
    but left the new colour defaults alone. It is a new screen in all but
    name, so it takes them too. Last in the module: it replaces the
    project (the module guard puts the seeded one back)."""
    pg, errors = page
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_timeout(1500)
    state = pg.evaluate("""() => { const app = window.app; return {
        pristine: app.project.is_pristine, n: app.project.layers.length,
        name: app.project.name, id: app.currentLayer && app.currentLayer.id }; }""")
    assert state['pristine'] is True and state['n'] == 1 and state['name'] == 'Untitled Project', state
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_timeout(300)

    def _tab(key):
        pg.locator(f'#preferences-modal .pm-tabstrip .view-tab[data-key="{key}"]').click()
        pg.wait_for_timeout(150)
    for prop, key in LAYER_OF.items():
        pid = next(p for p, (k, _s, _w) in PICKERS.items() if k == key)
        _tab('look' if pid in ('pref-screen-name-color', 'pref-cabinet-id-color')
             else 'data' if pid.startswith('pref-data-') else 'power')
        el = pg.locator(f'#{pid}')
        el.fill(COLOURS[key].lower())
        el.dispatch_event('change')
    _tab('power')
    for letter, value in zip('abcdef', COLOURS['powerCircuitColors']):
        el = pg.locator(f'#pref-power-circuit-color-{letter}')
        el.fill(value.lower())
        el.dispatch_event('change')
    pg.locator('#preferences-save').click()
    pg.wait_for_timeout(1000)
    live = pg.evaluate("() => window.app.project.layers[0]")
    assert _colours_of(live) == COLOURS_AS_LAYER, 'the startup screen kept the shipped colours'
    srv = pg.evaluate("async () => (await (await fetch('/api/project')).json()).layers[0]")
    assert _colours_of(srv) == COLOURS_AS_LAYER, 'the server did not get the colours'
    assert errors == [], errors


OLD_SHIPPED_CIRCUIT_COLORS = ['#BC382F', '#CC6B30', '#D2E94D', '#79FC4C', '#2145DC', '#7414F5']


def test_a_chosen_old_green_stays_and_an_untouched_old_set_migrates(page):
    """Item 1 (re-test): normalizePowerCircuitColors migrated every #79FC4C
    in D to the shipped green, so a preference set to the old green on
    purpose was repainted on every reload. The rule now: D migrates only
    when the stored map is, letter for letter, the OLD shipped set (a
    screen nobody coloured); any letter that differs or is missing keeps
    the green; and a green equal to the preference's D was chosen and
    stays whatever the rest holds - through a reload. The maps here are
    checked against an UNVERSIONED project ({}: a file saved before the
    app_version stamp), which is the only kind the migration runs on."""
    pg, errors = page
    old_set = dict(zip('ABCDEF', OLD_SHIPPED_CIRCUIT_COLORS))
    shipped = dict(zip('ABCDEF', SHIPPED_CIRCUIT_COLORS))
    pg.evaluate(SET_PREFS_JS, {'powerCircuitColors': SHIPPED_CIRCUIT_COLORS})
    got = pg.evaluate("""(old) => {
        const app = window.app;
        const lower = Object.fromEntries(Object.entries(old).map(([k, v]) => [k, v.toLowerCase()]));
        const noF = { ...old };
        delete noF.F;
        return {
            whole: app.normalizePowerCircuitColors(old, {}),
            lower: app.normalizePowerCircuitColors(lower, {}),
            aDiffers: app.normalizePowerCircuitColors({ ...old, A: '#111111' }, {}),
            fMissing: app.normalizePowerCircuitColors(noF, {}),
            dOnly: app.normalizePowerCircuitColors({ D: '#79FC4C' }, {}),
        };
    }""", old_set)
    assert got['whole'] == shipped, got['whole']
    assert got['lower'] == shipped, got['lower']
    assert got['aDiffers'] == dict(old_set, A='#111111'), got['aDiffers']
    assert got['fMissing'] == old_set, got['fMissing']
    assert got['dOnly'] == dict(shipped, D='#79FC4C'), got['dOnly']
    # the preference set to the old green: the whole old set still stays
    chosen = list(SHIPPED_CIRCUIT_COLORS)
    chosen[3] = '#79FC4C'
    pg.evaluate(SET_PREFS_JS, {'powerCircuitColors': chosen})
    kept = pg.evaluate("(old) => window.app.normalizePowerCircuitColors(old, {})", old_set)
    assert kept == old_set, kept
    # and a screen made from it keeps the green through a reload
    before = pg.evaluate(IDS_JS)
    pg.evaluate("() => window.app.addLayer()")
    pg.wait_for_timeout(1500)
    srv = pg.evaluate(SERVER_NEW_JS, before)
    assert 'error' not in srv, srv
    assert srv['powerCircuitColors'] == dict(zip('ABCDEF', chosen)), srv['powerCircuitColors']
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    live = pg.evaluate(CLIENT_NEW_JS, before)
    assert 'error' not in live, live
    assert live['powerCircuitColors']['D'] == '#79FC4C', 'the reload repainted the chosen old green'
    _delete(pg, srv['id'])
    pg.evaluate(SET_PREFS_JS, {'powerCircuitColors': SHIPPED_CIRCUIT_COLORS})
    assert errors == [], errors


def test_a_preset_with_junk_colour_keys_takes_the_defaults(page):
    """Item 3 (re-test): only null and '' were skipped, so a preset's
    'nope', 'red', [] or {} landed on the new screen (and 'nope' reached
    the server as labelsColor through addLayer's `||`). Every preset
    colour now goes through normalizeHexColor with the preference default
    behind it; a valid one lands upper case; the circuit map is checked a
    letter at a time, and [] is no map."""
    pg, errors = page
    pg.evaluate(SET_PREFS_JS, COLOURS)

    def _add(preset):
        before = pg.evaluate(IDS_JS)
        pg.evaluate("(p) => window.app.addLayer(p)", preset)
        pg.wait_for_timeout(1500)
        live = pg.evaluate(CLIENT_NEW_JS, before)
        assert 'error' not in live, live
        srv = pg.evaluate(SERVER_NEW_JS, before)
        assert 'error' not in srv, srv
        return live, srv

    live, srv = _add({
        'columns': 2, 'rows': 2, '_presetName': 'junk colours',
        'labelsColor': 'nope', 'cabinetIdColor': 'red',
        'arrowColor': [], 'dataFlowColor': {}, 'primaryColor': 'red', 'backupTextColor': 'nope',
        'powerLineColor': [], 'powerLabelBgColor': {}, 'powerLabelTextColor': 'nope',
        'powerCircuitColors': [], 'border_color_data': 'red',
        'border_color_pixel': '#0b0b0b',
        'bitDepth': 10,
    })
    assert _colours_of(live) == COLOURS_AS_LAYER, live
    assert _colours_of(srv) == COLOURS_AS_LAYER, srv
    assert (live['border_color_data'] or '').upper() == '#FFFFFF', live['border_color_data']
    assert live['border_color_pixel'] == '#0B0B0B', 'a valid preset colour lands, upper case'
    assert live['bitDepth'] == 10 and live['columns'] == 2, 'the rest of the preset still applies'
    _delete(pg, live['id'])
    live, srv = _add({'columns': 2, 'rows': 2, 'powerCircuitColors': {}})
    assert live['powerCircuitColors'] == COLOURS_AS_LAYER['powerCircuitColors'], live['powerCircuitColors']
    assert srv['powerCircuitColors'] == COLOURS_AS_LAYER['powerCircuitColors'], srv['powerCircuitColors']
    _delete(pg, live['id'])
    live, srv = _add({'columns': 2, 'rows': 2, 'powerCircuitColors': {'A': 'red', 'B': '#0b0b0b'}})
    want = dict(COLOURS_AS_LAYER['powerCircuitColors'], B='#0B0B0B')
    assert live['powerCircuitColors'] == want, live['powerCircuitColors']
    assert srv['powerCircuitColors'] == want, srv['powerCircuitColors']
    _delete(pg, live['id'])
    assert errors == [], errors


def test_junk_tile_preferences_never_reach_the_server(page):
    """Item 5 (re-test): a stored color1 of '#FFF' parsed in the picker
    but hexToRgb read it as red, and a borderColor of '' went to the
    server as border_color and as all four per-view borders. The three
    tile colours take the same check the new colours do: '#FFF' expands,
    anything else that is not a colour falls back to the shipped literal
    - in the dialog, on Save, and in addLayer."""
    pg, errors = page
    pg.evaluate(SET_PREFS_JS, {'color1': '#FFF', 'color2': 'nope', 'borderColor': ''})
    before = pg.evaluate(IDS_JS)
    pg.evaluate("() => window.app.addLayer()")
    pg.wait_for_timeout(1500)
    srv = pg.evaluate(SERVER_NEW_JS, before)
    assert 'error' not in srv, srv
    assert srv['color1'] == {'r': 255, 'g': 255, 'b': 255}, srv['color1']
    assert srv['color2'] == {'r': 149, 'g': 156, 'b': 184}, srv['color2']
    borders = ['border_color', 'border_color_pixel', 'border_color_cabinet',
               'border_color_data', 'border_color_power']
    assert [srv.get(k) for k in borders] == ['#FFFFFF'] * 5, {k: srv.get(k) for k in borders}
    _delete(pg, srv['id'])
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_timeout(300)
    shown = pg.evaluate("(ids) => ids.map(id => document.getElementById(id).value)",
                        ['pref-color1', 'pref-color2', 'pref-border-color'])
    assert shown == ['#ffffff', '#959cb8', '#ffffff'], shown
    pg.locator('#preferences-save').click()
    pg.wait_for_timeout(600)
    served = pg.evaluate("async () => (await (await fetch('/api/preferences')).json())")
    assert (served['color1'], served['color2'], served['borderColor']) == \
        ('#FFFFFF', '#959CB8', '#FFFFFF'), served
    pg.evaluate(SET_PREFS_JS, {'color1': '#404680', 'color2': '#959CB8', 'borderColor': '#FFFFFF'})
    assert errors == [], errors


def test_a_failed_push_after_add_is_logged_not_thrown(page):
    """Item 6 (re-test): the PUT that follows every add had no catch, so
    offline (or any failed PUT) every added screen raised an unhandled
    rejection. The failure is logged and shown; nothing throws, and the
    screen still lands in the browser."""
    pg, errors = page
    pg.evaluate("""() => {
        window.__rejections = [];
        window.addEventListener('unhandledrejection', e => window.__rejections.push(String(e.reason)));
    }""")

    def _abort_puts(route):
        if route.request.method == 'PUT':
            route.abort()
        else:
            route.continue_()
    pg.route('**/api/layer/*', _abort_puts)
    before = pg.evaluate(IDS_JS)
    try:
        pg.evaluate("() => window.app.addLayer()")
        pg.wait_for_timeout(1500)
    finally:
        pg.unroute('**/api/layer/*')
    rejections = pg.evaluate("() => window.__rejections")
    assert rejections == [], rejections
    toast = pg.evaluate("() => { const h = document.getElementById('app-toast-host'); return h ? h.textContent : ''; }")
    assert 'not saved' in toast, toast
    live = pg.evaluate(CLIENT_NEW_JS, before)
    assert 'error' not in live, live
    _delete(pg, live['id'])
    assert errors == [], errors


def _save_columns(pg, n):
    """Set the Wall tab's Columns preference to n and Save."""
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_timeout(300)
    pg.locator('#preferences-modal .pm-tabstrip .view-tab[data-key="wall"]').click()
    pg.wait_for_timeout(150)
    el = pg.locator('#pref-columns')
    el.fill(str(n))
    el.dispatch_event('change')
    pg.locator('#preferences-save').click()
    pg.wait_for_timeout(1000)


# The startup screen's columns in the browser and on the server, and the
# pristine flag on both sides.
STARTUP_STATE_JS = """async () => {
    const app = window.app;
    const srv = await (await fetch('/api/project')).json();
    return { live: app.project.layers[0].columns, srv: srv.layers[0].columns,
             pristine: app.project.is_pristine, srvPristine: srv.is_pristine };
}"""


def _edit_columns(pg, n):
    """The user types columns on the Screen Info panel."""
    pg.evaluate("""(n) => {
        const el = document.getElementById('screen-columns');
        el.value = String(n);
        el.dispatchEvent(new Event('change'));
    }""", n)
    pg.wait_for_timeout(1000)


def test_a_preference_save_follows_the_startup_screen_until_it_is_edited_across_relaunches(page):
    """Round three: the pristine startup screen (never edited) follows the
    Preferences dialog's Save until the user edits it - and that must
    hold after the app is launched fresh and reloaded, not only inside
    the session that made the screen. Until 2026-09-22 the client's own
    raster sync POST on every load cleared is_pristine on the server, so
    a relaunch stopped the screen following. Now: a fresh server project
    plus a page load, Save follows; reload, Save still follows and the
    server still says pristine; the user edits columns, Save leaves the
    screen alone and the server flag is false; New Project in-session
    behaves the same. Replaces the project (the module guard puts the
    seeded one back)."""
    pg, errors = page
    # the app launched fresh: a new SERVER project, then the page booting on it
    pg.evaluate("async () => { await fetch('/api/project/new', { method: 'POST' }); }")
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    state = pg.evaluate("""() => { const app = window.app; return {
        pristine: app.project.is_pristine, n: app.project.layers.length, name: app.project.name }; }""")
    assert state == {'pristine': True, 'n': 1, 'name': 'Untitled Project'}, state

    _save_columns(pg, 3)
    assert pg.evaluate(STARTUP_STATE_JS) == \
        {'live': 3, 'srv': 3, 'pristine': True, 'srvPristine': True}, 'the first Save did not follow'
    # relaunched: the page reloads on the same server project
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    assert pg.evaluate(STARTUP_STATE_JS)['srvPristine'] is True, 'the reload itself ended the pristine state'
    _save_columns(pg, 4)
    assert pg.evaluate(STARTUP_STATE_JS) == \
        {'live': 4, 'srv': 4, 'pristine': True, 'srvPristine': True}, 'the Save after a relaunch did not follow'
    # the user edits the screen on the Screen Info panel
    _edit_columns(pg, 6)
    got = pg.evaluate(STARTUP_STATE_JS)
    assert got['live'] == 6 and got['srv'] == 6, got
    assert got['srvPristine'] is False, 'the edit did not end the pristine state on the server'
    _save_columns(pg, 5)
    assert pg.evaluate(STARTUP_STATE_JS) == \
        {'live': 6, 'srv': 6, 'pristine': False, 'srvPristine': False}, 'the Save re-made the edited screen'
    # and after a relaunch the edited screen is still left alone
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    _save_columns(pg, 7)
    assert pg.evaluate(STARTUP_STATE_JS) == \
        {'live': 6, 'srv': 6, 'pristine': False, 'srvPristine': False}, 'the relaunch forgot the edit'

    # New Project in-session: the same, start to finish
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_timeout(1500)
    assert pg.evaluate(STARTUP_STATE_JS)['srvPristine'] is True, 'New Project ended its own pristine state'
    _save_columns(pg, 3)
    assert pg.evaluate(STARTUP_STATE_JS) == \
        {'live': 3, 'srv': 3, 'pristine': True, 'srvPristine': True}, 'a Save on the new project did not follow'
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    _save_columns(pg, 4)
    assert pg.evaluate(STARTUP_STATE_JS) == \
        {'live': 4, 'srv': 4, 'pristine': True, 'srvPristine': True}, 'the new project stopped following after a reload'
    _edit_columns(pg, 6)
    _save_columns(pg, 5)
    assert pg.evaluate(STARTUP_STATE_JS) == \
        {'live': 6, 'srv': 6, 'pristine': False, 'srvPristine': False}, 'the Save re-made the edited new project'
    pg.evaluate(SET_PREFS_JS, {'columns': 8})
    assert errors == [], errors


def test_a_failed_add_is_logged_and_toasted_not_thrown(page):
    """Round three, item 3: the POST /api/layer/add chain had no catch, so
    an add that failed (offline, the server gone) was an unhandled
    rejection on the page. It is logged and toasted; nothing throws and
    nothing is added."""
    pg, errors = page
    pg.evaluate("""() => {
        window.__rejections = [];
        window.addEventListener('unhandledrejection', e => window.__rejections.push(String(e.reason)));
    }""")
    before = pg.evaluate(IDS_JS)
    pg.route('**/api/layer/add', lambda route: route.abort())
    try:
        pg.evaluate("() => window.app.addLayer()")
        pg.wait_for_timeout(1500)
    finally:
        pg.unroute('**/api/layer/add')
    assert pg.evaluate("() => window.__rejections") == []
    toast = pg.evaluate("() => { const h = document.getElementById('app-toast-host'); return h ? h.textContent : ''; }")
    assert 'not added' in toast, toast
    assert pg.evaluate(IDS_JS) == before, 'a screen landed from a failed add'
    # a server error answers JSON too; the chain must not go on to select a layer with no id
    pg.route('**/api/layer/add', lambda route: route.fulfill(
        status=500, content_type='application/json', body='{"error": "boom"}'))
    try:
        pg.evaluate("() => window.app.addLayer()")
        pg.wait_for_timeout(1500)
    finally:
        pg.unroute('**/api/layer/add')
    assert pg.evaluate("() => window.__rejections") == []
    assert pg.evaluate(IDS_JS) == before, 'a screen landed from a 500'
    assert errors == [], errors


def test_a_presets_tile_colours_take_the_same_check_as_the_rest(page):
    """Round three, item 4: a preset's color1 / color2 skipped the check
    (`presetData.color1 || color1`), so 'nope' reached the server and drew
    grey. Now a well-formed {r, g, b} lands as is, a hex string (3 or 6
    digits, # or not) becomes the object the canvas draws from, and the
    rest fall back to the preference's colour."""
    pg, errors = page
    pg.evaluate(SET_PREFS_JS, {'color1': '#404680', 'color2': '#959CB8'})
    cases = [
        ({'color1': 'nope', 'color2': ''}, {'r': 64, 'g': 70, 'b': 128}, {'r': 149, 'g': 156, 'b': 184}),
        ({'color1': '#abc', 'color2': 'AABBCC'}, {'r': 170, 'g': 187, 'b': 204}, {'r': 170, 'g': 187, 'b': 204}),
        ({'color1': {'r': 1, 'g': 2, 'b': 3}, 'color2': {'r': 300, 'g': 2, 'b': 3}},
         {'r': 1, 'g': 2, 'b': 3}, {'r': 149, 'g': 156, 'b': 184}),
        ({'color1': [1, 2, 3], 'color2': {'r': 'x'}}, {'r': 64, 'g': 70, 'b': 128}, {'r': 149, 'g': 156, 'b': 184}),
    ]
    for preset, want1, want2 in cases:
        before = pg.evaluate(IDS_JS)
        pg.evaluate("(preset) => window.app.addLayer({ columns: 2, rows: 2, _presetName: 'tiles', ...preset })", preset)
        pg.wait_for_timeout(1500)
        srv = pg.evaluate(SERVER_NEW_JS, before)
        assert 'error' not in srv, srv
        assert srv['color1'] == want1, (preset, srv['color1'])
        assert srv['color2'] == want2, (preset, srv['color2'])
        _delete(pg, srv['id'])
    assert errors == [], errors


def test_normalize_tile_color_does_what_its_comment_says(page):
    """Round three, item 5: the comment said 'abc' falls back while the
    code accepted bare 3- and 6-digit hex and numbers. The rule is now
    stated and held: hex with or without '#', 3 digits doubled, upper
    case; everything else falls back."""
    pg, errors = page
    got = pg.evaluate("""() => {
        const app = window.app;
        const n = (v) => app.normalizeTileColor(v, '#FALLBK');
        return {
            abc: n('abc'), hashAbc: n('#abc'), six: n('aabbcc'), hashSix: n('#AaBbCc'),
            number: n(123), padded: n('  #fff '),
            xyz: n('xyz'), five: n('#12345'), red: n('red'), empty: n(''),
            nil: n(null), undef: n(undefined), obj: n({ r: 1, g: 2, b: 3 }), zero: n(0)
        };
    }""")
    assert got == {
        'abc': '#AABBCC', 'hashAbc': '#AABBCC', 'six': '#AABBCC', 'hashSix': '#AABBCC',
        'number': '#112233', 'padded': '#FFFFFF',
        'xyz': '#FALLBK', 'five': '#FALLBK', 'red': '#FALLBK', 'empty': '#FALLBK',
        'nil': '#FALLBK', 'undef': '#FALLBK', 'obj': '#FALLBK', 'zero': '#FALLBK',
    }, got
    comment = _read(PREFS_JS).split('normalizeTileColor(value, fallback) {')[0].rsplit('\n\n', 1)[-1]
    assert "with or without the '#'" in comment and "'abc' is '#AABBCC'" in comment, comment
    assert errors == [], errors


# ── app_version and the old-green migration gate ─────────────────────────


def _load_file(pg, project, name='file.json'):
    """Drive File > Open with an in-memory project, the way the user does."""
    with pg.expect_file_chooser() as chooser:
        pg.evaluate("() => window.app.loadProjectFromFile()")
    chooser.value.set_files({'name': name, 'mimeType': 'application/json',
                             'buffer': json.dumps(project).encode('utf-8')})
    pg.wait_for_timeout(2000)


def test_the_old_green_migrates_only_for_a_project_an_older_build_wrote(page):
    """Round three, item 2: a preset or a copy carrying the whole old
    shipped set was migrated on the next open because the rule could not
    tell it from an untouched old file. The project's app_version - the
    build that last wrote it - decides: none, or older than 1.3.0,
    migrates (the exact-old-set rule stays the fallback for unversioned
    files); 1.3.0 or later never does."""
    pg, errors = page
    old_set = dict(zip('ABCDEF', OLD_SHIPPED_CIRCUIT_COLORS))
    shipped = dict(zip('ABCDEF', SHIPPED_CIRCUIT_COLORS))
    pg.evaluate(SET_PREFS_JS, {'powerCircuitColors': SHIPPED_CIRCUIT_COLORS})
    got = pg.evaluate("""(old) => {
        const app = window.app;
        const at = (v) => app.normalizePowerCircuitColors(old, v === undefined ? {} : { app_version: v });
        return {
            none: at(undefined), empty: at(''), junk: at('yesterday'),
            older: at('1.2.9'), olderMajor: at('0.11.4'), betaOlder: at('v1.2.0-beta.3'),
            exact: at('1.3.0'), newer: at('1.3.1'), newerMinor: at('1.10.0'), newerMajor: at('2.0.0'),
            betaExact: at('1.3.0-beta.1'), vExact: at('v1.3.0'),
            predates: ['', '1.2.9', '1.3.0', '2.0.0', undefined].map(v =>
                app.projectPredatesVersion('1.3.0', v === undefined ? {} : { app_version: v })),
        };
    }""", old_set)
    for key in ('none', 'empty', 'junk', 'older', 'olderMajor', 'betaOlder'):
        assert got[key] == shipped, (key, got[key])
    for key in ('exact', 'newer', 'newerMinor', 'newerMajor', 'betaExact', 'vExact'):
        assert got[key] == old_set, (key, got[key])
    assert got['predates'] == [True, True, False, False, True], got['predates']
    assert errors == [], errors


def test_a_saved_file_carries_the_app_version_and_a_load_reads_it_back(page):
    """Round three, item 2: the file the app writes is stamped with the
    running build's version (the same /api/version the About dialog
    shows), the server hands it back after File > Open, and a project the
    server built carries it from the first sync. Replaces the project (the
    module guard puts the seeded one back)."""
    pg, errors = page
    version = pg.evaluate("async () => (await (await fetch('/api/version')).json()).version")
    assert re.match(r'^\d+\.\d+\.\d+', version or ''), version
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_timeout(1500)
    live = pg.evaluate("async () => ({ client: window.app.project.app_version,"
                       " server: (await (await fetch('/api/project')).json()).app_version,"
                       " title: window.app.appVersion() })")
    assert live == {'client': version, 'server': version, 'title': version}, live
    saved = json.loads(pg.evaluate("() => window.app.serializeProjectForFile()"))
    assert saved['app_version'] == version, saved.get('app_version')
    saved['name'] = 'Round Trip'
    _load_file(pg, saved, 'round-trip.json')
    back = pg.evaluate("async () => ({ name: window.app.project.name, client: window.app.project.app_version,"
                       " server: (await (await fetch('/api/project')).json()).app_version })")
    assert back == {'name': 'Round Trip', 'client': version, 'server': version}, back
    assert errors == [], errors


def _load_with_old_set(pg, project, name):
    """File > Open on `project` with its one screen painted the whole old
    shipped set; the circuit map the browser and the server then hold."""
    project = dict(project, name=name)
    project['layers'][0] = dict(project['layers'][0],
                                powerCircuitColors=dict(zip('ABCDEF', OLD_SHIPPED_CIRCUIT_COLORS)))
    _load_file(pg, project, name.lower().replace(' ', '-') + '.json')
    got = pg.evaluate("async () => ({ name: window.app.project.name,"
                      " live: window.app.project.layers[0].powerCircuitColors,"
                      " srv: (await (await fetch('/api/project')).json()).layers[0].powerCircuitColors })")
    assert got['name'] == name, got
    return got


def test_an_old_file_with_the_old_set_migrates_and_a_stamped_one_does_not(page):
    """Round three, item 2, through File > Open: an unversioned file whose
    screen carries the whole old shipped set opens with the shipped green
    in D; the same file stamped by a 1.3.0 build opens with the old green
    it holds, and keeps it through a reload (the server holds the stamp).
    Replaces the project (the module guard puts the seeded one back)."""
    pg, errors = page
    old_set = dict(zip('ABCDEF', OLD_SHIPPED_CIRCUIT_COLORS))
    pg.evaluate(SET_PREFS_JS, {'powerCircuitColors': SHIPPED_CIRCUIT_COLORS})
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_timeout(1500)
    project = json.loads(pg.evaluate("() => window.app.serializeProjectForFile()"))

    unversioned = dict(project)
    del unversioned['app_version']
    got = _load_with_old_set(pg, unversioned, 'Old File')
    assert got['live']['D'] == SHIPPED_CIRCUIT_COLORS[3], got['live']
    assert got['srv']['D'] == SHIPPED_CIRCUIT_COLORS[3], got['srv']

    got = _load_with_old_set(pg, dict(project, app_version='1.2.9'), 'Older File')
    assert got['live']['D'] == SHIPPED_CIRCUIT_COLORS[3], got['live']

    got = _load_with_old_set(pg, dict(project, app_version='1.3.0'), 'Stamped File')
    assert got['live'] == old_set, got['live']
    assert got['srv'] == old_set, got['srv']
    pg.reload(wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    live = pg.evaluate("() => window.app.project.layers[0].powerCircuitColors")
    assert live == old_set, live
    assert errors == [], errors


def test_a_file_this_build_saves_is_never_migrated_on_its_next_open(page):
    """Round three, item 2, the contract behind the gate: the build that
    writes app_version must be one the migration leaves alone, or every
    file it saves with the old set (a preset, a copy) is repainted on its
    next open - the very defect. The migration runs for files older than
    1.3.0, so the running build must be 1.3.0 or later: bump README,
    VERSION.txt, index.html and the spec together. Replaces the project
    (the module guard puts the seeded one back)."""
    pg, errors = page
    old_set = dict(zip('ABCDEF', OLD_SHIPPED_CIRCUIT_COLORS))
    pg.evaluate(SET_PREFS_JS, {'powerCircuitColors': SHIPPED_CIRCUIT_COLORS})
    pg.evaluate("() => window.app.createNewProject()")
    pg.wait_for_timeout(1500)
    project = json.loads(pg.evaluate("() => window.app.serializeProjectForFile()"))
    version = project.get('app_version')
    assert not pg.evaluate("(v) => window.app.projectPredatesVersion('1.3.0', { app_version: v })", version), \
        f'this build is {version}: a file it saves would be migrated on its next open - bump to 1.3.0 or later'
    got = _load_with_old_set(pg, project, 'Current File')
    assert got['live'] == old_set, got['live']
    assert got['srv'] == old_set, got['srv']
    assert errors == [], errors
