"""The Preferences dialog: seven tabs, every field once, Save / Cancel /
Reset Defaults at the foot - and every new default honoured only where the
app CREATES something (a distro, a binder block on a project with no
values of its own, a snake, a loose port cable, a power cable).

Run locally (each session takes its own free port, so it runs beside any
other):
    python3 -m pytest tests/test_preferences.py -v --browser chromium
"""

import pytest


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project (and its preferences) the way this
    module found them."""


# The seven tabs, in the order the strip shows them, with the field ids
# each holds. Every id today's dialog had keeps its id; the new ones are
# the mock's (mocks/preferences-mock.html?layout=tabs).
TABS = {
    'wall': ['pref-raster-width', 'pref-raster-height', 'pref-columns', 'pref-rows',
             'pref-panel-width', 'pref-panel-height', 'pref-panel-width-mm',
             'pref-panel-height-mm', 'pref-panel-weight', 'pref-weight-unit',
             'pref-canvas-gap'],
    'look': ['pref-color1', 'pref-color2', 'pref-border-color', 'pref-screen-name-color',
             'pref-cabinet-id-color', 'pref-font',
             'pref-cabinet-font-size', 'pref-label-font-size', 'pref-data-label-size',
             'pref-power-label-size'],
    'data': ['pref-processor-type', 'pref-low-latency', 'pref-bit-depth', 'pref-frame-rate',
             'pref-data-flow-pattern-grid', 'pref-data-line-width',
             'pref-data-line-color', 'pref-data-arrow-color',
             'pref-data-primary-color', 'pref-data-primary-text-color',
             'pref-data-backup-color', 'pref-data-backup-text-color'],
    'power': ['pref-power-flow-pattern-grid', 'pref-power-line-width',
              'pref-power-voltage-select', 'pref-power-voltage-custom',
              'pref-power-amperage-select', 'pref-power-amperage-custom', 'pref-power-watts',
              'pref-power-line-color', 'pref-power-arrow-color',
              'pref-power-label-bg-color', 'pref-power-label-text-color',
              'pref-power-circuit-color-a', 'pref-power-circuit-color-b',
              'pref-power-circuit-color-c', 'pref-power-circuit-color-d',
              'pref-power-circuit-color-e', 'pref-power-circuit-color-f'],
    'distros': ['pref-distro-rating', 'pref-distro-voltage', 'pref-distro-phase',
                'pref-multi-type', 'pref-breakout-type', 'pref-splitters-enabled'],
    'binder': ['pref-binder-sheet', 'pref-binder-screen-order', 'pref-binder-colour',
               'pref-binder-printer', 'pref-binder-side-power', 'pref-binder-side-data',
               'pref-binder-side-both', 'pref-binder-cover', 'pref-binder-pull',
               'pref-binder-hardware', 'pref-binder-wiring', 'pref-binder-title-block',
               'pref-binder-designer', 'pref-binder-pm-name', 'pref-binder-pm-phone',
               'pref-binder-pm-email', 'pref-binder-drafter', 'pref-binder-logo'],
    'pull': ['pref-pull-engineer', 'pref-pull-rev', 'pref-pull-power-jump-name',
             'pref-pull-power-jump-length', 'pref-pull-data-jump-name',
             'pref-pull-data-jump-length', 'pref-snake-home-run-length',
             'pref-loose-port-cable-length', 'pref-power-cable-length'],
}
ALL_IDS = [i for ids in TABS.values() for i in ids]
assert len(ALL_IDS) == 83

# Issue 28: the colour defaults a NEW screen starts with, id -> (the colour
# the dialog is given, the preference key, the layer property it lands on).
# A colour picker hands back lower-case hex; the preference stores it the
# way a layer does, upper case.
COLOR_FIELDS = [
    ('pref-screen-name-color', '#112233', 'screenNameColor', 'labelsColor'),
    ('pref-cabinet-id-color', '#223344', 'cabinetIdColor', 'cabinetIdColor'),
    ('pref-data-line-color', '#334455', 'dataLineColor', 'dataFlowColor'),
    ('pref-data-arrow-color', '#445566', 'dataArrowColor', 'arrowColor'),
    ('pref-data-primary-color', '#556677', 'dataPrimaryColor', 'primaryColor'),
    ('pref-data-primary-text-color', '#667788', 'dataPrimaryTextColor', 'primaryTextColor'),
    ('pref-data-backup-color', '#778899', 'dataBackupColor', 'backupColor'),
    ('pref-data-backup-text-color', '#8899aa', 'dataBackupTextColor', 'backupTextColor'),
    ('pref-power-line-color', '#99aabb', 'powerLineColor', 'powerLineColor'),
    ('pref-power-arrow-color', '#aabbcc', 'powerArrowColor', 'powerArrowColor'),
    ('pref-power-label-bg-color', '#bbccdd', 'powerLabelBgColor', 'powerLabelBgColor'),
    ('pref-power-label-text-color', '#ccddee', 'powerLabelTextColor', 'powerLabelTextColor'),
]
CIRCUIT_COLORS = ['#a10001', '#a20002', '#a30003', '#a40004', '#a50005', '#a60006']

# What today's dialog had (36 ids, the three buttons and the modal among
# them) - every one of them stays.
TODAY = ['preferences-modal', 'pref-raster-width', 'pref-raster-height', 'pref-columns',
         'pref-rows', 'pref-panel-width', 'pref-panel-height', 'pref-panel-width-mm',
         'pref-panel-height-mm', 'pref-panel-weight', 'pref-weight-unit',
         'pref-cabinet-font-size', 'pref-label-font-size', 'pref-color1', 'pref-color2',
         'pref-border-color', 'pref-font', 'pref-data-flow-pattern-grid',
         'pref-power-flow-pattern-grid', 'pref-data-line-width', 'pref-power-line-width',
         'pref-data-label-size', 'pref-power-label-size', 'pref-processor-type',
         'pref-low-latency', 'pref-bit-depth', 'pref-frame-rate', 'pref-canvas-gap',
         'pref-power-voltage-select', 'pref-power-voltage-custom',
         'pref-power-amperage-select', 'pref-power-amperage-custom', 'pref-power-watts',
         'preferences-reset', 'preferences-cancel', 'preferences-save']

# A wall on an H9 card (its ports placed), and multi 1 of the same wall on
# a distro - so a snake, a loose port cable and a power cable can each be
# made where the app makes them.
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    proj.binder = {};
    proj.pullSheet = {};
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL', columns: 8, rows: 12,
                              cabinet_width: 200, cabinet_height: 200})});
    const post = (url, body) => fetch(url, {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)}).then(r => r.json());
    const put = (url, body) => fetch(url, {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)}).then(r => r.json());
    let st = await post('/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await put(`/api/processors/${pid}/slots/0`,
                   {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    const app = window.app;
    const p1 = await (await fetch('/api/project')).json();
    for (const l of p1.layers) {
        await put(`/api/layer/${l.id}`, {powerVoltage: 208, powerAmperage: 10,
                                         panelWatts: 200,
                                         processorType: 'novastar-armor'});
    }
    const p = await (await fetch('/api/project')).json();
    app.project = p;
    app.dedupeProjectLayers('prefs_setup');
    const wall = app.project.layers[0];
    app.selectLayer(wall);
    const d = app.addDistro({name: 'SR'});
    app.setSocaDistro(wall, 1, d.id);
    app.setSocaNumber(wall, 1, 1);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow',
                                 'POST', {layerId: String(wall.id), cardId});
    app.renderLayers();
    app._circuitTailCache = null;
    app.renderHardwareDock();
    const r = window.canvasRenderer;
    r.viewMode = 'power';
    r.zoom = 0.22; r.panX = 60; r.panY = 60; r.render();
    app.resetHistory('Prefs Seed');
    return { id: wall.id, procId: pid, cardId, distroId: d.id };
}"""

# The dialog as it stands: which tab is up, which sections show, whether
# the page scrolls, and where every visible field of the active tab sits
# against the body that holds it.
DIALOG_JS = """() => {
    const modal = document.getElementById('preferences-modal');
    const content = modal.querySelector('.modal-content');
    const body = modal.querySelector('.pm-body');
    const de = document.documentElement;
    const shown = [...modal.querySelectorAll('.pm-section')]
        .filter(s => getComputedStyle(s).display !== 'none').map(s => s.dataset.key);
    const active = [...modal.querySelectorAll('.pm-tabstrip .view-tab.active')]
        .map(t => t.dataset.key);
    const b = body.getBoundingClientRect();
    const c = content.getBoundingClientRect();
    const clipped = [];
    modal.querySelectorAll('.pm-section').forEach(sec => {
        if (getComputedStyle(sec).display === 'none') return;
        sec.querySelectorAll('input, select, button, .prefs-flow-grid').forEach(el => {
            if (el.offsetParent === null) return;   // display:none (custom V/A, file input)
            const r = el.getBoundingClientRect();
            if (r.top < b.top - 0.5 || r.bottom > b.bottom + 0.5
                || r.left < b.left - 0.5 || r.right > b.right + 0.5) {
                clipped.push({ id: el.id || el.className, top: r.top, bottom: r.bottom,
                               left: r.left, right: r.right });
            }
        });
    });
    return {
        open: getComputedStyle(modal).display !== 'none',
        shown, active,
        page: { sh: de.scrollHeight, ch: de.clientHeight, sw: de.scrollWidth, cw: de.clientWidth },
        body: { sh: body.scrollHeight, ch: body.clientHeight, top: b.top, bottom: b.bottom,
                height: b.height },
        content: { top: c.top, bottom: c.bottom, left: c.left, right: c.right },
        clipped,
        buttons: ['preferences-reset', 'preferences-cancel', 'preferences-save']
            .map(id => { const el = document.getElementById(id);
                         return el && el.offsetParent !== null ? el.textContent.trim() : null; }),
    };
}"""

# The new preference fields set by the round trip, id -> (value, key in
# /api/preferences, value the API should carry). Checkboxes and radios
# are booleans / choices.
NEW_FIELDS = [
    ('pref-distro-rating', '200', 'distroRatingA', 200),
    ('pref-distro-voltage', '120', 'distroVoltage', 120),
    ('pref-distro-phase', '1', 'distroPhase', 1),
    ('pref-multi-type', 'soca120', 'multiType', 'soca120'),
    ('pref-breakout-type', 'soca-edison', 'breakoutType', 'soca-edison'),
    ('pref-splitters-enabled', True, 'splittersEnabled', True),
    ('pref-binder-sheet', 'letter', 'binderSheet', 'letter'),
    ('pref-binder-screen-order', 'power', 'binderScreenOrder', 'power'),
    ('pref-binder-printer', True, 'binderPalette', 'printer'),
    ('pref-binder-side-data', True, 'binderMaps', 'data'),
    ('pref-binder-cover', False, 'binderCover', False),
    ('pref-binder-pull', True, 'binderPull', True),
    ('pref-binder-hardware', False, 'binderHardware', False),
    ('pref-binder-wiring', True, 'binderWiring', True),
    ('pref-binder-title-block', False, 'binderTitleBlock', False),
    ('pref-binder-designer', 'Dee Signer', 'binderDesigner', 'Dee Signer'),
    ('pref-binder-pm-name', 'Pam Manager', 'binderPmName', 'Pam Manager'),
    ('pref-binder-pm-phone', '555-0100', 'binderPmPhone', '555-0100'),
    ('pref-binder-pm-email', 'pm@example.com', 'binderPmEmail', 'pm@example.com'),
    ('pref-binder-drafter', 'Dan Drafter', 'binderDrafter', 'Dan Drafter'),
    ('pref-pull-engineer', 'Ed Engineer', 'engineerName', 'Ed Engineer'),
    ('pref-pull-rev', '2.0', 'pullRev', '2.0'),
    ('pref-pull-power-jump-name', 'Power Jump X', 'powerJumpName', 'Power Jump X'),
    ('pref-pull-power-jump-length', '8', 'powerJumpLength', 8),
    ('pref-pull-data-jump-name', 'Data Jump X', 'dataJumpName', 'Data Jump X'),
    ('pref-pull-data-jump-length', '9', 'dataJumpLength', 9),
    ('pref-snake-home-run-length', '175', 'snakeHomeRunFt', 175),
    ('pref-loose-port-cable-length', '75', 'loosePortCableFt', 75),
    ('pref-power-cable-length', '12', 'powerCableFt', 12),
]


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e) + '\n' + str(getattr(e, 'stack', ''))))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1200)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _open(pg):
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_timeout(300)


def _tab(pg, key):
    pg.locator(f'#preferences-modal .pm-tabstrip .view-tab[data-key="{key}"]').click()
    pg.wait_for_timeout(150)


def _set(pg, field_id, value):
    el = pg.locator(f'#{field_id}')
    tag = el.evaluate('e => e.tagName')
    typ = el.evaluate('e => e.type || ""')
    if tag == 'SELECT':
        el.select_option(value)
    elif typ in ('checkbox', 'radio'):
        if value:
            el.check()
        else:
            el.uncheck()
    else:
        el.fill(str(value))
    el.dispatch_event('change')


def _read(pg, field_id):
    return pg.evaluate("""(id) => {
        const el = document.getElementById(id);
        if (el.type === 'checkbox' || el.type === 'radio') return el.checked;
        return el.value;
    }""", field_id)


def _served(pg):
    return pg.evaluate("async () => (await (await fetch('/api/preferences')).json())")


def _save(pg):
    pg.locator('#preferences-save').click()
    pg.wait_for_timeout(600)


# ── the dialog ────────────────────────────────────────────────────────────

def test_every_field_is_there_once_and_one_tab_shows_at_a_time(page):
    """All 65 field ids, no id twice, today's 36 among them; seven tabs in
    the mock's order, one section up at a time, the strip switching them;
    Reset Defaults / Cancel / Save at the foot."""
    pg, ids = page
    _open(pg)
    present = pg.evaluate("(ids) => ids.filter(i => !document.getElementById(i))", ALL_IDS + TODAY)
    assert present == [], f'missing: {present}'
    dup = pg.evaluate("""() => {
        const all = [...document.querySelectorAll('#preferences-modal [id]')].map(e => e.id);
        return all.filter((x, i) => all.indexOf(x) !== i);
    }""")
    assert dup == [], f'duplicate ids: {dup}'
    strip = pg.evaluate("""() => [...document.querySelectorAll(
        '#preferences-modal .pm-tabstrip .view-tab')].map(t => [t.dataset.key, t.textContent.trim()])""")
    assert strip == [['wall', 'Wall'], ['look', 'Look'], ['data', 'Data'], ['power', 'Power'],
                     ['distros', 'Distros & multis'], ['binder', 'Binder'],
                     ['pull', 'Pull sheet & cables']], strip
    for key, fields in TABS.items():
        _tab(pg, key)
        d = pg.evaluate(DIALOG_JS)
        assert d['shown'] == [key] and d['active'] == [key], (key, d['shown'], d['active'])
        # every field of this tab lives in the shown section
        home = pg.evaluate("""(ids) => ids.map(i => {
            const el = document.getElementById(i);
            const sec = el.closest('.pm-section');
            return sec ? sec.dataset.key : null; })""", fields)
        assert home == [key] * len(fields), (key, list(zip(fields, home)))
        assert d['buttons'] == ['Reset Defaults', 'Cancel', 'Save'], d['buttons']
    pg.locator('#preferences-cancel').click()
    assert ids['errors'] == [], ids['errors']


def test_the_strip_remembers_the_tab_within_the_session(page):
    pg, ids = page
    _open(pg)
    _tab(pg, 'binder')
    pg.locator('#preferences-cancel').click()
    pg.wait_for_timeout(200)
    _open(pg)
    d = pg.evaluate(DIALOG_JS)
    assert d['shown'] == ['binder'] and d['active'] == ['binder'], d
    pg.locator('#preferences-cancel').click()


def test_the_dialog_fits_1440_by_900_with_nothing_clipped(page):
    """No page scroll, the dialog inside the viewport, one body height on
    every tab, and no field of any tab outside the body that holds it."""
    pg, ids = page
    _open(pg)
    heights = set()
    for key in TABS:
        _tab(pg, key)
        d = pg.evaluate(DIALOG_JS)
        assert d['page']['sh'] <= d['page']['ch'] and d['page']['sw'] <= d['page']['cw'], (key, d['page'])
        assert d['content']['top'] >= 0 and d['content']['bottom'] <= 900, (key, d['content'])
        assert d['content']['left'] >= 0 and d['content']['right'] <= 1440, (key, d['content'])
        assert d['body']['sh'] <= d['body']['ch'] + 1, (key, d['body'])
        assert d['clipped'] == [], (key, d['clipped'])
        heights.add(round(d['body']['height']))
    assert len(heights) == 1, f'the body must keep one height across the tabs: {heights}'
    pg.locator('#preferences-cancel').click()


# ── the round trip ────────────────────────────────────────────────────────

def test_every_new_preference_round_trips(page):
    """Set in the UI -> Save -> /api/preferences carries it -> reopen shows
    it. Cancel after an edit leaves the stored value alone."""
    pg, ids = page
    _open(pg)
    for field_id, value, _key, _want in NEW_FIELDS:
        _tab(pg, next(k for k, f in TABS.items() if field_id in f))
        _set(pg, field_id, value)
    _save(pg)
    assert pg.evaluate("() => getComputedStyle(document.getElementById('preferences-modal')).display") == 'none'
    served = _served(pg)
    for field_id, _value, key, want in NEW_FIELDS:
        assert served.get(key) == want, (field_id, key, served.get(key), want)
    # the same values are what the app reads back
    live = pg.evaluate("() => window.app.getPreferences()")
    for _f, _v, key, want in NEW_FIELDS:
        assert live.get(key) == want, (key, live.get(key), want)
    _open(pg)
    for field_id, value, _key, _want in NEW_FIELDS:
        _tab(pg, next(k for k, f in TABS.items() if field_id in f))
        got = _read(pg, field_id)
        assert got == value, (field_id, got, value)
    # an edit then Cancel changes nothing stored
    _tab(pg, 'distros')
    _set(pg, 'pref-distro-rating', '999')
    pg.locator('#preferences-cancel').click()
    pg.wait_for_timeout(300)
    assert _served(pg)['distroRatingA'] == 200
    _open(pg)
    _tab(pg, 'distros')
    assert _read(pg, 'pref-distro-rating') == '200'
    pg.locator('#preferences-cancel').click()


def test_the_binder_logo_rides_the_save_and_not_the_cancel(page):
    """A logo chosen in the dialog is stored on Save (the same data URL the
    export dialog reads), not before; the Remove button clears it."""
    pg, ids = page
    png = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAD0lEQVQI12P4'
           'z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==')
    _open(pg)
    _tab(pg, 'binder')
    pg.evaluate("""(png) => {
        const bin = atob(png.split(',')[1]);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const file = new File([bytes], 'logo.png', { type: 'image/png' });
        const input = document.getElementById('pref-binder-logo');
        const dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }""", png)
    pg.wait_for_timeout(600)
    assert pg.locator('#pref-binder-logo-preview').is_visible()
    assert _served(pg).get('binderLogo', '') == '', 'nothing stored before Save'
    _save(pg)
    stored = _served(pg).get('binderLogo', '')
    assert stored.startswith('data:image/png;base64,'), stored[:40]
    assert pg.evaluate("() => window.app.getBinderLogo()") == stored
    _open(pg)
    _tab(pg, 'binder')
    assert pg.locator('#pref-binder-logo-preview').is_visible()
    pg.locator('#pref-binder-logo-remove').click()
    pg.wait_for_timeout(200)
    assert not pg.locator('#pref-binder-logo-preview').is_visible()
    pg.locator('#preferences-cancel').click()
    pg.wait_for_timeout(200)
    assert _served(pg).get('binderLogo', '') == stored, 'Cancel keeps the logo'
    _open(pg)
    _tab(pg, 'binder')
    pg.locator('#pref-binder-logo-remove').click()
    _save(pg)
    assert _served(pg).get('binderLogo', '') == ''


# ── the defaults, honoured at creation ────────────────────────────────────

def test_a_new_distro_takes_the_preference(page):
    """After the round trip above the preference says 200 A, 120 V, 1φ:
    Add distro makes one so; a distro that exists keeps what it had."""
    pg, ids = page
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    before = pg.evaluate("(id) => window.app.getDistros().find(d => d.id === id)", ids['distroId'])
    # the + Add distro button's own handler: addDistro, then the naming pass
    made = pg.evaluate("() => { const app = window.app; const d = app.addDistro();"
                       " app._restateNaming(); app.renderHardwareDock(); return d; }")
    pg.wait_for_timeout(500)
    assert (made['ratingA'], made['voltage'], made['phase']) == (200, 120, 1), made
    after = pg.evaluate("(id) => window.app.getDistros().find(d => d.id === id)", ids['distroId'])
    assert (after['ratingA'], after['voltage'], after['phase']) == \
        (before['ratingA'], before['voltage'], before['phase']) == (400, 208, 3), (before, after)
    head = pg.evaluate("""(id) => {
        const u = document.querySelector(`.hw-dock-distro[data-lrd-distro="${id}"]`);
        return u ? u.textContent : null; }""", made['id'])
    assert head and '120V·1φ' in head and '/200 A' in head, head
    pg.evaluate("(id) => window.app.removeDistro(id)", made['id'])
    pg.wait_for_timeout(300)


def test_a_new_multi_box_takes_the_preference_type(page):
    """A spare box on a distro that has nothing typed, no member and no
    neighbour reads the preference's multi type (Multi 120 after the round
    trip); a box with a stored type keeps it."""
    pg, ids = page
    d = pg.evaluate("() => window.app.addDistro({name: 'SPARE'})")
    got = pg.evaluate("(id) => { const app = window.app; const d = app.getDistros().find(x => x.id === id);"
                      " const r = app.distroBoxType(d, 1); return [r.type.id, r.source]; }", d['id'])
    assert got == ['soca120', 'default'], got
    pg.evaluate("(id) => window.app.setDistroBoxType(id, 1, 'l2130')", d['id'])
    got = pg.evaluate("(id) => { const app = window.app; const d = app.getDistros().find(x => x.id === id);"
                      " const r = app.distroBoxType(d, 1); return [r.type.id, r.source]; }", d['id'])
    assert got == ['l2130', 'stored'], got
    pg.evaluate("(id) => window.app.removeDistro(id)", d['id'])
    pg.wait_for_timeout(300)


def test_a_new_screen_takes_the_breakout_and_splitter_preferences(page):
    """After the round trip the preference says Multi -> Edison (110V) and
    splitters on. A new screen at 110 V (the power preference) takes both;
    the existing WALL keeps its own."""
    pg, ids = page
    wall_before = pg.evaluate("(id) => { const l = window.app.project.layers.find(x => x.id === id);"
                              " return [l.powerBreakoutType || null, (l.powerSplitters || {}).enabled]; }", ids['id'])
    n = pg.evaluate("() => window.app.project.layers.length")
    pg.evaluate("() => window.app.addLayer()")
    pg.wait_for_timeout(1200)
    made = pg.evaluate("(n) => { const l = window.app.project.layers; if (l.length <= n) return null;"
                       " const s = l[l.length - 1]; return { id: s.id, v: s.powerVoltage,"
                       " breakout: s.powerBreakoutType || null, splitters: s.powerSplitters.enabled }; }", n)
    assert made, 'no screen was added'
    assert made['v'] == 110, made
    assert made['breakout'] == 'soca-edison' and made['splitters'] is True, made
    wall_after = pg.evaluate("(id) => { const l = window.app.project.layers.find(x => x.id === id);"
                             " return [l.powerBreakoutType || null, (l.powerSplitters || {}).enabled]; }", ids['id'])
    assert wall_after == wall_before, (wall_before, wall_after)
    pg.evaluate("(id) => window.app.deleteLayer(id)", made['id'])
    pg.wait_for_timeout(800)
    pg.evaluate("(id) => { const app = window.app; app.selectLayer(app.project.layers.find(x => x.id === id)); }",
                ids['id'])


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


def test_a_new_screen_ends_on_an_eligible_breakout(page):
    """Item 8 (re-test): a breakout preference the voltage does not allow
    (L21-30 at 110 V, Edison at 208 V) was skipped and left the new
    screen with no breakout at all, and a preset carrying an ineligible
    breakout landed it raw. addLayer now runs normalizePowerBreakout
    after the preference and the preset, so the screen ends on the
    eligible default - Edison at or below 120 V, True1 above - on the
    client and on the server; an eligible choice still lands as chosen."""
    pg, ids = page
    saved = pg.evaluate("() => window.app.getPreferences()")

    def _add(preset):
        n = pg.evaluate("() => window.app.project.layers.length")
        pg.evaluate("(p) => window.app.addLayer(p)", preset)
        pg.wait_for_timeout(1200)
        made = pg.evaluate("""async (n) => {
            const l = window.app.project.layers;
            if (l.length <= n) return null;
            const s = l[l.length - 1];
            const srv = (await (await fetch('/api/project')).json()).layers.find(x => x.id === s.id);
            return { id: s.id, v: s.powerVoltage, live: s.powerBreakoutType || null,
                     srv: srv ? (srv.powerBreakoutType || null) : 'missing' };
        }""", n)
        assert made, 'no screen was added'
        pg.evaluate("(id) => window.app.deleteLayer(id)", made['id'])
        pg.wait_for_timeout(800)
        return made

    # the preference
    for breakout, voltage, want in [('l2130-true1', 110, 'soca-edison'),
                                    ('soca-edison', 208, 'soca-true1'),
                                    ('soca-powercon', 208, 'soca-powercon')]:
        pg.evaluate(SET_PREFS_JS, {'breakoutType': breakout, 'powerVoltage': voltage})
        made = _add(None)
        assert made['v'] == voltage, (breakout, voltage, made)
        assert (made['live'], made['srv']) == (want, want), (breakout, voltage, made)
    # a preset
    for breakout, voltage, want in [('l2130-true1', 120, 'soca-edison'),
                                    ('soca-edison', 208, 'soca-true1'),
                                    ('l2130-powercon', 208, 'l2130-powercon')]:
        made = _add({'columns': 2, 'rows': 2, '_presetName': 'breakout',
                     'powerVoltage': voltage, 'powerBreakoutType': breakout})
        assert made['v'] == voltage, (breakout, voltage, made)
        assert (made['live'], made['srv']) == (want, want), (breakout, voltage, made)
    pg.evaluate(SET_PREFS_JS, {'breakoutType': saved['breakoutType'], 'powerVoltage': saved['powerVoltage']})
    pg.evaluate("(id) => { const app = window.app; app.selectLayer(app.project.layers.find(x => x.id === id)); }",
                ids['id'])


def test_the_export_dialog_binder_block_opens_with_the_preferences(page):
    """On a project with no binder values of its own the Binder block shows
    the preferences; a value the project has wins over the preference."""
    pg, ids = page
    pg.evaluate("() => { window.app.project.binder = {}; }")
    pg.evaluate("() => window.app.openExportModal('binder')")
    pg.wait_for_timeout(300)
    got = pg.evaluate("""() => {
        const v = id => document.getElementById(id).value;
        const on = id => document.getElementById(id).checked;
        return { sheet: v('export-binder-sheet'), order: v('export-binder-screen-order'),
                 printer: on('export-binder-printer'), data: on('export-binder-side-data'),
                 cover: on('export-binder-cover'), pull: on('export-binder-pull'),
                 hardware: on('export-binder-hardware'), wiring: on('export-binder-wiring'),
                 block: on('export-binder-title-block'),
                 designer: v('export-binder-designer'), pm: v('export-binder-pm-name'),
                 phone: v('export-binder-pm-phone'), email: v('export-binder-pm-email'),
                 drafter: v('export-binder-drafter'), engineer: v('export-binder-engineer'),
                 rev: v('export-binder-rev') };
    }""")
    assert got == {'sheet': 'letter', 'order': 'power', 'printer': True, 'data': True,
                   'cover': False, 'pull': True, 'hardware': False, 'wiring': True, 'block': False,
                   'designer': 'Dee Signer', 'pm': 'Pam Manager', 'phone': '555-0100',
                   'email': 'pm@example.com', 'drafter': 'Dan Drafter', 'engineer': 'Ed Engineer',
                   'rev': '2.0'}, got
    # the export reads the same block the dialog shows
    info = pg.evaluate("() => window.app.getBinderInfo()")
    assert info['designer'] == 'Dee Signer' and info['screenOrder'] == 'power', info
    assert pg.evaluate("() => window.app.getPullSheetSettings()") == {
        'dataJumpName': 'Data Jump X', 'dataJumpLength': 9, 'powerJumpName': 'Power Jump X',
        'powerJumpLength': 8, 'rev': '2.0'}
    pg.locator('#export-cancel').click()
    # the project's own values win where set, the preference fills the rest
    pg.evaluate("""() => { const app = window.app;
        app.setBinderField('designer', 'Show Designer');
        app.setBinderField('screenOrder', 'layers');
        app.setPullSheetSetting('rev', '3.1'); }""")
    pg.evaluate("() => window.app.openExportModal('binder')")
    pg.wait_for_timeout(300)
    got = pg.evaluate("""() => {
        const v = id => document.getElementById(id).value;
        return [v('export-binder-designer'), v('export-binder-screen-order'),
                v('export-binder-pm-name'), v('export-binder-rev')]; }""")
    assert got == ['Show Designer', 'layers', 'Pam Manager', '3.1'], got
    assert pg.evaluate("() => window.app.project.binder") == {'designer': 'Show Designer',
                                                             'screenOrder': 'layers'}
    pg.locator('#export-cancel').click()


def test_new_cables_take_the_preference_length(page):
    """A snake formed now is 175'; the loose-port quick fill reads and
    writes 75'; the power quick fill reads and writes 12' - the lengths
    the round trip set. Nothing already typed changes."""
    pg, ids = page
    cid = ids['cardId']
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    made = pg.evaluate("""async (cid) => {
        const app = window.app;
        const owner = app._dataCableOwner('card', cid);
        const id = await app.snakePorts(app.snakeMembersOf(owner, [1, 2]));
        const s = app.getShowSnake(id);
        return { id, ft: s.ft, n: s.members.length };
    }""", cid)
    assert made['ft'] == 175 and made['n'] == 2, made
    # the loose-port quick fill on the card's sheet
    pg.evaluate("(cid) => { const app = window.app; const o = app._dataCableOwner('card', cid);"
                " app._setDataCableSheetOpen(o, true); app.renderHardwareDock(); }", cid)
    pg.wait_for_timeout(400)
    btn = pg.locator(f'[data-lrd-field="data-cable-fill-{cid}-75"]')
    assert btn.count() == 1 and btn.text_content().strip() == "all 75'"
    btn.click()
    pg.wait_for_timeout(600)
    cables = pg.evaluate("(cid) => window.app._dataCableOwner('card', cid).rec.portCables", cid)
    assert cables.get('3', {}).get('ft') == 75, cables
    assert '1' not in cables and '2' not in cables, 'snaked sockets keep the snake'
    # the power quick fill on the box's sheet
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    pg.locator(f'[data-lrd-field="power-cable-sheet-{ids["distroId"]}-1"]').click()
    pg.wait_for_timeout(400)
    fill = pg.locator(f'[data-lrd-field="power-cable-fill-{ids["distroId"]}-1-12"]')
    assert fill.count() == 1 and fill.text_content().strip() == "all 12'"
    pg.evaluate("(id) => { const app = window.app; const l = app.project.layers.find(x => x.id === id);"
                " app.setCircuitCable(l, 2, { ft: 30, connector: null }); }", ids['id'])
    fill.click()
    pg.wait_for_timeout(600)
    cables = pg.evaluate("(id) => window.app.project.layers.find(x => x.id === id).powerCircuitCables",
                         ids['id'])
    assert cables.get('1') == {'ft': 12, 'connector': None}, cables
    assert cables.get('2') == {'ft': 12, 'connector': None}, 'the fill is every circuit on the box'
    # a typed length is never rewritten by a preference change
    _open(pg)
    _tab(pg, 'pull')
    _set(pg, 'pref-power-cable-length', '40')
    _save(pg)
    cables = pg.evaluate("(id) => window.app.project.layers.find(x => x.id === id).powerCircuitCables",
                         ids['id'])
    assert cables.get('1') == {'ft': 12, 'connector': None}, cables
    assert pg.evaluate("(id) => window.app.getShowSnake(id).ft", made['id']) == 175


def test_a_new_screen_takes_the_colour_preferences(page):
    """Issue 28: every colour picker on the Look, Data and Power tabs is a
    default for a NEW screen - the screen name, the cabinet ID text, the
    data line, arrow and port labels, the power line, arrow and circuit
    label, and the six circuit colours A to F. Set them, Save, add a
    screen: the screen carries them. The existing WALL keeps its own."""
    pg, ids = page
    wall_before = pg.evaluate("(id) => { const l = window.app.project.layers.find(x => x.id === id);"
                              " return [l.labelsColor, l.cabinetIdColor, l.dataFlowColor, l.arrowColor,"
                              " l.powerLineColor, l.powerLabelBgColor, l.powerCircuitColors]; }", ids['id'])
    _open(pg)
    for field_id, value, _key, _prop in COLOR_FIELDS:
        _tab(pg, next(k for k, f in TABS.items() if field_id in f))
        _set(pg, field_id, value)
    _tab(pg, 'power')
    for letter, value in zip('abcdef', CIRCUIT_COLORS):
        _set(pg, f'pref-power-circuit-color-{letter}', value)
    _save(pg)
    served = _served(pg)
    for field_id, value, key, _prop in COLOR_FIELDS:
        assert served.get(key) == value.upper(), (field_id, key, served.get(key))
    assert served.get('powerCircuitColors') == [c.upper() for c in CIRCUIT_COLORS], served.get('powerCircuitColors')
    assert pg.evaluate("() => window.app.getDefaultPowerCircuitColors()") == dict(
        zip('ABCDEF', [c.upper() for c in CIRCUIT_COLORS]))
    # reopened, the pickers show what was saved
    _open(pg)
    for field_id, value, _key, _prop in COLOR_FIELDS:
        _tab(pg, next(k for k, f in TABS.items() if field_id in f))
        assert _read(pg, field_id) == value, field_id
    _tab(pg, 'power')
    for letter, value in zip('abcdef', CIRCUIT_COLORS):
        assert _read(pg, f'pref-power-circuit-color-{letter}') == value, letter
    pg.locator('#preferences-cancel').click()
    pg.wait_for_timeout(200)
    # a new screen starts with them
    n = pg.evaluate("() => window.app.project.layers.length")
    pg.evaluate("() => window.app.addLayer()")
    pg.wait_for_timeout(1200)
    made = pg.evaluate("(n) => { const l = window.app.project.layers; if (l.length <= n) return null;"
                       " return l[l.length - 1]; }", n)
    assert made, 'no screen was added'
    for field_id, value, _key, prop in COLOR_FIELDS:
        assert (made.get(prop) or '').lower() == value, (field_id, prop, made.get(prop))
    assert made['powerCircuitColors'] == dict(zip('ABCDEF', [c.upper() for c in CIRCUIT_COLORS])), \
        made['powerCircuitColors']
    # the server's copy of the new screen carries the two it sets itself
    srv = pg.evaluate("async (id) => (await (await fetch('/api/project')).json())"
                      ".layers.find(l => l.id === id)", made['id'])
    assert (srv['labelsColor'].lower(), srv['cabinetIdColor'].lower()) == ('#112233', '#223344'), srv
    # a screen that exists is untouched
    wall_after = pg.evaluate("(id) => { const l = window.app.project.layers.find(x => x.id === id);"
                             " return [l.labelsColor, l.cabinetIdColor, l.dataFlowColor, l.arrowColor,"
                             " l.powerLineColor, l.powerLabelBgColor, l.powerCircuitColors]; }", ids['id'])
    assert wall_after == wall_before, (wall_before, wall_after)
    pg.evaluate("(id) => window.app.deleteLayer(id)", made['id'])
    pg.wait_for_timeout(800)
    pg.evaluate("(id) => { const app = window.app; app.selectLayer(app.project.layers.find(x => x.id === id)); }",
                ids['id'])


# ── Reset Defaults ────────────────────────────────────────────────────────

def test_reset_defaults_asks_first_and_lands_on_save(page):
    """Reset asks yes/no. No: nothing changes. Yes: every tab shows its
    shipped default, and only Save writes them; Cancel after a Yes keeps
    what was stored."""
    pg, ids = page
    stored = _served(pg)
    assert stored['distroRatingA'] == 200 and stored['binderDesigner'] == 'Dee Signer', stored
    defaults = pg.evaluate("() => window.app.getPreferencesDefaults()")
    asked = []
    _open(pg)
    _tab(pg, 'wall')
    _set(pg, 'pref-columns', '11')

    def say_no(dialog):
        asked.append(dialog.message)
        dialog.dismiss()
    pg.once('dialog', say_no)
    pg.locator('#preferences-reset').click()
    pg.wait_for_timeout(300)
    assert asked == ['Put every preference back to its default?'], asked
    assert _read(pg, 'pref-columns') == '11'
    _tab(pg, 'distros')
    assert _read(pg, 'pref-distro-rating') == '200'

    def say_yes(dialog):
        asked.append(dialog.message)
        dialog.accept()
    pg.once('dialog', say_yes)
    pg.locator('#preferences-reset').click()
    pg.wait_for_timeout(300)
    assert len(asked) == 2
    assert _read(pg, 'pref-distro-rating') == '400'
    assert _read(pg, 'pref-distro-voltage') == '208' and _read(pg, 'pref-distro-phase') == '3'
    _tab(pg, 'wall')
    assert _read(pg, 'pref-columns') == '8'
    _tab(pg, 'binder')
    assert _read(pg, 'pref-binder-designer') == '' and _read(pg, 'pref-binder-colour') is True
    assert _read(pg, 'pref-binder-cover') is True and _read(pg, 'pref-binder-title-block') is True
    _tab(pg, 'pull')
    assert _read(pg, 'pref-pull-rev') == '1.0' and _read(pg, 'pref-pull-engineer') == ''
    # a Yes is an edit like any other: Cancel discards it
    pg.locator('#preferences-cancel').click()
    pg.wait_for_timeout(300)
    assert _served(pg)['distroRatingA'] == 200, 'Cancel after a Yes keeps the stored values'
    _open(pg)
    pg.once('dialog', say_yes)
    pg.locator('#preferences-reset').click()
    pg.wait_for_timeout(300)
    _save(pg)
    served = _served(pg)
    # a colour input hands back its hex in lower case; the same colour
    norm = lambda d: {k: (v.lower() if isinstance(v, str) and v.startswith('#') else v)
                      for k, v in d.items()}
    served, defaults = norm(served), norm(defaults)
    assert served == defaults, {k: (served.get(k), defaults.get(k))
                                for k in set(served) | set(defaults) if served.get(k) != defaults.get(k)}
    assert ids['errors'] == [], ids['errors']
