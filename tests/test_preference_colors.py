"""Issue 28: the colour defaults for a new screen, read from the sources.

Every colour picker the Preferences dialog gained (Look: screen name and
cabinet ID text; Data: line, arrow, primary and backup port; Power: line,
arrow, circuit label, circuits A to F) is one id in index.html, one key in
getPreferencesDefaults, one setVal in fillPreferencesUI, one readColor in
readPreferencesFromUI, and one read in initializeLayerDefaults (or, for
the two the server sets, in addLayer's request). A picker that misses any
of those is a swatch that does nothing; this test says which.

The browser round trip (set, Save, add a screen) is in test_preferences.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(ROOT, 'src', 'templates', 'index.html')
PREFS_JS = os.path.join(ROOT, 'src', 'static', 'js', 'app-preferences.js')
PRESETS_JS = os.path.join(ROOT, 'src', 'static', 'js', 'app-presets.js')
CORE_JS = os.path.join(ROOT, 'src', 'static', 'js', 'app-core.js')
NAMING_JS = os.path.join(ROOT, 'src', 'static', 'js', 'app-naming.js')

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


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _section(html, key):
    m = re.search(r'<section class="pm-section" id="pm-sec-%s".*?</section>' % key, html, re.S)
    assert m, key
    return m.group(0)


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
    for label in ('Tile colors', 'Cabinet border', 'Labels', 'Cabinet ID text'):
        assert f'<label>{label}</label>' in look, label
    assert '<label>Colors</label>' not in look


def test_every_colour_picker_has_a_default_a_load_and_a_save():
    js = _read(PREFS_JS)
    defaults = js[js.index('getPreferencesDefaults() {'):js.index('getLocalPreferences() {')]
    fill = js[js.index('fillPreferencesUI(prefs) {'):js.index('readPreferencesFromUI() {')]
    read = js[js.index('readPreferencesFromUI() {'):js.index('_webSafeFonts() {')]
    for pid, (key, shipped, _where) in PICKERS.items():
        assert re.search(r'^\s+%s: \'%s\',' % (key, shipped), defaults, re.M), (key, shipped)
        assert f"setVal('{pid}', prefs.{key});" in fill, pid
        assert f"{key}: readColor('{pid}', defaults.{key})," in read, pid
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
            # the server sets these two on create_layer; the request carries the preference
            prop = {'screenNameColor': 'labelsColor', 'cabinetIdColor': 'cabinetIdColor'}[key]
            assert f'{prop}: prefs.{key}' in add, (pid, prop)
            assert f'{prop}: presetData.{prop} || prefs.{key}' in add, (pid, prop)
            assert f'prefs.{key}' not in init, f'{key} is the server\'s to set'
        else:
            assert f"layer.{where} = color(prefs.{key}, '{shipped}');" in init, (pid, where)
    assert 'layer.powerCircuitColors = this.getDefaultPowerCircuitColors();' in init
    naming = _read(NAMING_JS)
    fn = naming[naming.index('getDefaultPowerCircuitColors() {'):naming.index('normalizeHexColor(value')]
    assert 'const list = this.getPreferenceCircuitColorList();' in fn
    assert 'return { A: list[0], B: list[1], C: list[2], D: list[3], E: list[4], F: list[5] };' in fn
    for colour in SHIPPED_CIRCUIT_COLORS:
        assert colour not in fn, 'the shipped circuit colours live in app-preferences now'
