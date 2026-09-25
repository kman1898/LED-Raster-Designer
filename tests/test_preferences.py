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
              'pref-power-circuit-color-e', 'pref-power-circuit-color-f',
              # the breakout default sits under the default voltage it is
              # gated by (2026-09-22: "that should be set in preferences")
              'pref-breakout-type'],
    'distros': ['pref-distro-rating', 'pref-distro-voltage', 'pref-distro-phase',
                'pref-multi-type', 'pref-splitters-enabled'],
    'binder': ['pref-binder-sheet', 'pref-binder-screen-order', 'pref-binder-colour',
               'pref-binder-printer', 'pref-binder-side-power', 'pref-binder-side-data',
               'pref-binder-side-both', 'pref-binder-cover', 'pref-binder-pull',
               'pref-binder-hardware', 'pref-binder-wiring', 'pref-binder-title-block',
               'pref-binder-designer', 'pref-binder-pm-name', 'pref-binder-pm-phone',
               'pref-binder-pm-email', 'pref-binder-drafter', 'pref-binder-logo'],
    'pull': ['pref-pull-engineer', 'pref-pull-rev', 'pref-pull-power-jump-name',
             'pref-pull-power-jump-length', 'pref-pull-power-jump-length-h',
             'pref-pull-data-jump-name', 'pref-pull-data-jump-length',
             'pref-pull-data-jump-length-h', 'pref-snake-home-run-length',
             'pref-loose-port-cable-length', 'pref-power-cable-length'],
}
ALL_IDS = [i for ids in TABS.values() for i in ids]
assert len(ALL_IDS) == 85

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
    ('pref-pull-power-jump-length-h', '7', 'powerJumpLengthH', 7),
    ('pref-pull-data-jump-name', 'Data Jump X', 'dataJumpName', 'Data Jump X'),
    ('pref-pull-data-jump-length', '9', 'dataJumpLength', 9),
    ('pref-pull-data-jump-length-h', '1.5', 'dataJumpLengthH', 1.5),
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
    after the preference and the preset, so the screen ends eligible on
    the client and on the server: the preference where the voltage
    allows it, else the class default - Edison at or below 120 V, True1
    above; an eligible choice still lands as chosen."""
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
    # a preset, under a powerCON preference (eligible at every voltage):
    # an ineligible preset breakout lands on the preference
    for breakout, voltage, want in [('l2130-true1', 120, 'soca-powercon'),
                                    ('soca-edison', 208, 'soca-powercon'),
                                    ('l2130-powercon', 208, 'l2130-powercon')]:
        made = _add({'columns': 2, 'rows': 2, '_presetName': 'breakout',
                     'powerVoltage': voltage, 'powerBreakoutType': breakout})
        assert made['v'] == voltage, (breakout, voltage, made)
        assert (made['live'], made['srv']) == (want, want), (breakout, voltage, made)
    # ... and under a preference the voltage refuses, on the class default
    pg.evaluate(SET_PREFS_JS, {'breakoutType': 'l2130-true1', 'powerVoltage': 208})
    for breakout, voltage, want in [('l2130-true1', 120, 'soca-edison'),
                                    ('soca-edison', 230, 'soca-true1'),
                                    ('soca-edison', 208, 'l2130-true1')]:
        made = _add({'columns': 2, 'rows': 2, '_presetName': 'breakout',
                     'powerVoltage': voltage, 'powerBreakoutType': breakout})
        assert made['v'] == voltage, (breakout, voltage, made)
        assert (made['live'], made['srv']) == (want, want), (breakout, voltage, made)
    pg.evaluate(SET_PREFS_JS, {'breakoutType': saved['breakoutType'], 'powerVoltage': saved['powerVoltage']})
    pg.evaluate("(id) => { const app = window.app; app.selectLayer(app.project.layers.find(x => x.id === id)); }",
                ids['id'])


def test_normalize_prefers_the_preference_breakout_on_both_sides(page):
    """The write-in order (user ruling, 2026-09-22: "if 208 is default
    then True1 is default, but that should be set in preferences"): a
    stored eligible choice stands; else the Preferences breakout when the
    screen's voltage allows it; else the class default. The client's
    normalizePowerBreakout and the server's PUT answer the same."""
    pg, ids = page
    saved = pg.evaluate("() => window.app.getPreferences()")
    cases = [
        # (preference, voltage, stored) -> written
        ('soca-powercon', 110, None, 'soca-powercon'),
        ('soca-powercon', 208, '', 'soca-powercon'),
        ('soca-powercon', 230, 'soca-edison', 'soca-powercon'),
        ('soca-powercon', 120, 'l2130-true1', 'soca-powercon'),
        ('soca-powercon', 120, 'soca-edison', 'soca-edison'),      # eligible, stands
        ('l2130-true1', 208, None, 'l2130-true1'),
        ('l2130-true1', 110, None, 'soca-edison'),                 # class default
        ('l2130-true1', 230, 'soca-edison', 'soca-true1'),         # class default
        ('l2130-true1', 208, 'soca-l620', 'soca-l620'),            # eligible, stands
        ('soca-edison', 208, None, 'soca-true1'),
        ('soca-edison', 100, 'junk', 'soca-edison'),
        ('soca-l620', 120, None, 'soca-edison'),
        ('soca-l620', 121, None, 'soca-l620'),
    ]
    try:
        for pref, voltage, stored, want in cases:
            pg.evaluate(SET_PREFS_JS, {'breakoutType': pref})
            out = pg.evaluate("""async ([id, voltage, stored]) => {
                const app = window.app;
                const l = app.project.layers.find(x => x.id === id);
                const keep = { v: l.powerVoltage, bt: l.powerBreakoutType };
                const probe = { type: 'screen', powerVoltage: voltage };
                if (stored !== null) probe.powerBreakoutType = stored;
                app.normalizePowerBreakout(probe);
                const body = { powerVoltage: voltage, powerBreakoutType: stored };
                const srv = await (await fetch(`/api/layer/${id}`, { method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body) })).json();
                await fetch(`/api/layer/${id}`, { method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(keep) });
                return [probe.powerBreakoutType, srv.powerBreakoutType];
            }""", [ids['id'], voltage, stored])
            assert out == [want, want], (pref, voltage, stored, out)
    finally:
        pg.evaluate(SET_PREFS_JS, {'breakoutType': saved['breakoutType']})


def test_the_breakout_preference_is_gated_by_the_voltage_preference(page):
    """In the dialog the breakout select sits under the default voltage
    and follows it with the sidebar select's own rule and reasons: at 208
    V Edison is greyed (and the L21-30 boxes open), at 110 V L6-20 and
    the L21-30 boxes are greyed, at a custom 121 V Edison and the L21-30
    boxes are greyed. A selection the new voltage refuses snaps to the
    class default, and Save stores the gated pair."""
    pg, ids = page
    saved = pg.evaluate("() => window.app.getPreferences()")
    _open(pg)
    _tab(pg, 'power')
    read = """() => {
        const sel = document.getElementById('pref-breakout-type');
        const opts = {};
        [...sel.options].forEach(o => { opts[o.value] = [o.disabled, o.title]; });
        return { value: sel.value, opts,
                 visible: sel.offsetParent !== null,
                 underVoltage: sel.getBoundingClientRect().top
                     > document.getElementById('pref-power-voltage-select').getBoundingClientRect().top };
    }"""
    try:
        _set(pg, 'pref-power-voltage-select', '208')
        _set(pg, 'pref-breakout-type', 'l2130-true1')
        st = pg.evaluate(read)
        assert st['visible'] and st['underVoltage'], st
        assert st['value'] == 'l2130-true1', st
        assert st['opts']['soca-edison'] == [True, 'Not available at 208V — Edison is for screens up to 120V.'], st
        assert st['opts']['l2130-powercon'][0] is False and st['opts']['soca-l620'][0] is False, st
        # 110 V: the L21-30 pick snaps to Edison, the class default
        _set(pg, 'pref-power-voltage-select', '110')
        st = pg.evaluate(read)
        assert st['value'] == 'soca-edison', st
        for gone in ('soca-l620', 'l2130-true1', 'l2130-powercon'):
            assert st['opts'][gone][0] is True, (gone, st)
        assert st['opts']['l2130-true1'][1] == 'Not available at 110V — L21-30 is 208V only.', st
        assert st['opts']['soca-l620'][1] == \
            'Not available at 110V — a screen up to 120V runs Multi → True1, powerCON or Edison.', st
        for ok in ('soca-true1', 'soca-powercon', 'soca-edison'):
            assert st['opts'][ok] == [False, ''], (ok, st)
        # a custom 121 V (committed on change, never per keystroke - see
        # test_a_custom_voltage_typed_digit_by_digit_keeps_the_breakout_pick):
        # Edison snaps to True1, the L21-30 boxes stay out
        _set(pg, 'pref-power-voltage-select', 'custom')
        pg.evaluate("""() => {
            const box = document.getElementById('pref-power-voltage-custom');
            box.value = '121';
            box.dispatchEvent(new Event('change', { bubbles: true }));
        }""")
        st = pg.evaluate(read)
        assert st['value'] == 'soca-true1', st
        assert st['opts']['soca-edison'][0] is True and st['opts']['l2130-true1'][0] is True, st
        assert st['opts']['soca-l620'][0] is False, st
        # a pick the voltage allows is what Save stores, with the voltage
        _set(pg, 'pref-breakout-type', 'soca-l620')
        _save(pg)
        served = _served(pg)
        assert (served['powerVoltage'], served['breakoutType']) == (121, 'soca-l620'), served
        # reopening shows the pair, still gated
        _open(pg)
        _tab(pg, 'power')
        st = pg.evaluate(read)
        assert st['value'] == 'soca-l620' and st['opts']['soca-edison'][0] is True, st
        pg.locator('#preferences-cancel').click()
        pg.wait_for_timeout(200)
    finally:
        pg.evaluate(SET_PREFS_JS, {'breakoutType': saved['breakoutType'], 'powerVoltage': saved['powerVoltage']})
        pg.evaluate("""() => {
            const m = document.getElementById('preferences-modal');
            if (m) m.style.display = 'none';
        }""")


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
        'dataJumpName': 'Data Jump X', 'powerJumpName': 'Power Jump X', 'rev': '2.0'}
    # the jumper LENGTHS are per screen: the preferences are what a new
    # screen starts with (vertical / horizontal, data and power)
    assert pg.evaluate("() => window.app.jumperDefaults()") == {
        'dataJumpV': 9, 'dataJumpH': 1.5, 'powerJumpV': 8, 'powerJumpH': 7}
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


# ── the preferences route stores only an object ───────────────────────────

def test_the_preferences_route_refuses_a_body_that_is_not_an_object(page):
    """PUT /api/preferences stored ANY JSON body (2026-09-23): a list
    became the preferences record and the next POST /api/canvas 500'd on
    reading canvasGap off it. A body that is not a JSON object is refused
    with 400, the stored record stands, and the routes that read it still
    answer."""
    pg, ids = page
    before = _served(pg)
    assert isinstance(before, dict) and before, before
    got = pg.evaluate("""async (bodies) => {
        const out = [];
        for (const body of bodies) {
            const r = await fetch('/api/preferences', { method: 'PUT',
                headers: { 'Content-Type': 'application/json' }, body });
            out.push([body, r.status]);
        }
        out.push(['not json', (await fetch('/api/preferences', { method: 'PUT',
            headers: { 'Content-Type': 'application/json' }, body: '{nope' })).status]);
        out.push(['no body', (await fetch('/api/preferences', { method: 'PUT' })).status]);
        return out;
    }""", ['[]', '[1, 2]', '"junk"', '42', 'null', 'true'])
    assert all(status == 400 for _, status in got), got
    assert _served(pg) == before, 'a refused body replaced the preferences'
    made = pg.evaluate("""async () => {
        const r = await fetch('/api/canvas', { method: 'POST',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'After' }) });
        const data = await r.json();
        const canvases = data.canvases || [];
        const c = canvases.find(x => x.name === 'After');
        const del = c ? (await fetch(`/api/canvas/${c.id}`, { method: 'DELETE' })).status : null;
        return { status: r.status, found: !!c, del };
    }""")
    assert made == {'status': 200, 'found': True, 'del': 200}, made
    # an object still lands
    pg.evaluate(SET_PREFS_JS, {})
    assert _served(pg) == before


def test_a_junk_breakout_preference_does_not_leak_the_donor_s_voltage(page):
    """Preferences at 120 V with a breakout id the catalog does not know,
    and a 208 V screen already on the canvas: the new screen lands at
    120 V on Edison - the class default - on the client AND the server.
    Before (2026-09-23) the server seeded the new layer with the donor's
    208 V and normalized there to True1, the client then wrote 120 V, and
    True1 - eligible at 120 V - stood."""
    pg, ids = page
    saved = pg.evaluate("() => window.app.getPreferences()")
    donor = pg.evaluate("(id) => window.app.project.layers.find(l => l.id === id).powerVoltage", ids['id'])
    assert donor == 208, donor
    pg.evaluate(SET_PREFS_JS, {'breakoutType': 'junk', 'powerVoltage': 120})
    try:
        n = pg.evaluate("() => window.app.project.layers.length")
        pg.evaluate("() => window.app.addLayer(null)")
        pg.wait_for_timeout(1500)
        made = pg.evaluate("""async (n) => {
            const l = window.app.project.layers;
            if (l.length <= n) return null;
            const s = l[l.length - 1];
            const srv = (await (await fetch('/api/project')).json()).layers.find(x => x.id === s.id);
            return { id: s.id, live: [s.powerVoltage, s.powerBreakoutType || null],
                     srv: srv ? [srv.powerVoltage, srv.powerBreakoutType || null] : 'missing' };
        }""", n)
        assert made, 'no screen was added'
        pg.evaluate("(id) => window.app.deleteLayer(id)", made['id'])
        pg.wait_for_timeout(800)
        assert made['live'] == [120, 'soca-edison'], made
        assert made['srv'] == [120, 'soca-edison'], made
    finally:
        pg.evaluate(SET_PREFS_JS, {'breakoutType': saved['breakoutType'], 'powerVoltage': saved['powerVoltage']})
        pg.evaluate("(id) => { const app = window.app; app.selectLayer(app.project.layers.find(x => x.id === id)); }",
                    ids['id'])


# ── the dialog's tabs and the workspace ───────────────────────────────────

# What the workspace shows: the renderer's view, the hardware dock (hidden
# by class outside Data / Power), the Power sidebar panel, and which top
# view tab is lit.
WORKSPACE_JS = """() => {
    const dock = document.getElementById('hardware-dock');
    const panel = document.querySelector('.tab-panel[data-tab="power"]');
    return { mode: window.canvasRenderer.viewMode,
             dockHidden: !!dock && dock.classList.contains('view-hidden'),
             powerPanel: panel ? getComputedStyle(panel).display : 'missing',
             lit: [...document.querySelectorAll('#view-tabs .view-tab.active')].map(t => t.dataset.mode) };
}"""


def test_the_dialog_s_tabs_leave_the_workspace_alone(page):
    """The dialog's tab strip reuses the .view-tab class (data-key, no
    data-mode). The workspace's view-tab wiring bound every .view-tab on
    the page, so clicking Power / Look / Data INSIDE the dialog called
    setViewMode(undefined): the hardware dock and every sidebar panel
    vanished until a top view button was clicked (2026-09-23). Open from
    Power view, click every dialog tab, Cancel: the view is still Power,
    the dock is not view-hidden, the Power panel is shown, Power is the
    lit top tab - and the dialog's own strip still switched sections."""
    pg, ids = page
    pg.locator('#view-tabs .view-tab[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    before = pg.evaluate(WORKSPACE_JS)
    assert before['mode'] == 'power' and before['dockHidden'] is False, before
    assert before['powerPanel'] == 'block' and before['lit'] == ['power'], before
    _open(pg)
    for key in TABS:
        _tab(pg, key)
        shown = pg.evaluate("""() => [...document.querySelectorAll('#preferences-modal .pm-section.active')]
            .map(s => s.dataset.key)""")
        assert shown == [key], (key, shown)
        assert pg.evaluate(WORKSPACE_JS) == before, (key, pg.evaluate(WORKSPACE_JS))
    pg.locator('#preferences-cancel').click()
    pg.wait_for_timeout(200)
    assert pg.evaluate(WORKSPACE_JS) == before
    assert pg.evaluate("() => window.app._prefsTab") == 'pull'
    assert ids['errors'] == [], ids['errors']


# ── the custom voltage box ────────────────────────────────────────────────

# The Power tab's voltage pair as the dialog shows it, the figure the
# gate reads (the one Save stores), and which breakouts are greyed.
VOLTAGE_UI_JS = """() => {
    const app = window.app;
    const sel = document.getElementById('pref-breakout-type');
    const box = document.getElementById('pref-power-voltage-custom');
    const greyed = [...sel.options].filter(o => o.disabled).map(o => o.value).sort();
    return { select: document.getElementById('pref-power-voltage-select').value,
             box: box.value, boxShown: box.style.display !== 'none',
             gate: app._preferenceVoltageInUI(), breakout: sel.value, greyed,
             read: [app.readPreferencesFromUI().powerVoltage, app.readPreferencesFromUI().breakoutType] };
}"""


def _box(pg, value, event='change'):
    pg.evaluate("""([v, ev]) => {
        const box = document.getElementById('pref-power-voltage-custom');
        box.value = v;
        box.dispatchEvent(new Event(ev, { bubbles: true }));
    }""", [value, event])
    pg.wait_for_timeout(100)
    return pg.evaluate(VOLTAGE_UI_JS)


def _restore_voltage_prefs(pg, saved):
    pg.evaluate(SET_PREFS_JS, {'breakoutType': saved['breakoutType'], 'powerVoltage': saved['powerVoltage']})
    pg.evaluate("""() => {
        const m = document.getElementById('preferences-modal');
        if (m) m.style.display = 'none';
    }""")


def test_a_blank_custom_voltage_gates_on_the_figure_save_stores(page):
    """(a) A blank custom box gated as 0 V - offering L6-20 and the rest -
    while Save fell back to 110 V and stored 110 / Edison: the pair shown
    was not the pair stored. Now the box, the gate and Save read one
    figure: a box with no figure stands for the figure in force (the last
    figure the box accepted - the stock 110 the select mirrored into it
    here, the stored custom 121 on the second open), the box shows it,
    and what Save stores is what the dialog showed."""
    pg, ids = page
    saved = pg.evaluate("() => window.app.getPreferences()")
    try:
        pg.evaluate(SET_PREFS_JS, {'powerVoltage': 110, 'breakoutType': 'soca-true1'})
        _open(pg)
        _tab(pg, 'power')
        _set(pg, 'pref-power-voltage-select', 'custom')
        st = _box(pg, '')
        assert st['box'] == '110' and st['gate'] == 110, st
        assert st['greyed'] == ['l2130-powercon', 'l2130-true1', 'soca-l620'], st
        assert st['read'] == [110, 'soca-true1'], st
        _set(pg, 'pref-breakout-type', 'soca-powercon')
        st = _box(pg, '')
        assert st['read'] == [110, 'soca-powercon'], st
        _save(pg)
        served = _served(pg)
        assert (served['powerVoltage'], served['breakoutType']) == (110, 'soca-powercon'), served
        # a stored custom figure is the figure in force on the next open
        pg.evaluate(SET_PREFS_JS, {'powerVoltage': 121, 'breakoutType': 'soca-l620'})
        _open(pg)
        _tab(pg, 'power')
        st = pg.evaluate(VOLTAGE_UI_JS)
        assert st['select'] == 'custom' and st['box'] == '121' and st['boxShown'], st
        st = _box(pg, '')
        assert st['box'] == '121' and st['gate'] == 121, st
        assert st['greyed'] == ['l2130-powercon', 'l2130-true1', 'soca-edison'], st
        assert st['read'] == [121, 'soca-l620'], st
        pg.locator('#preferences-cancel').click()
        pg.wait_for_timeout(200)
    finally:
        _restore_voltage_prefs(pg, saved)
    assert ids['errors'] == [], ids['errors']


def test_a_custom_voltage_is_whole_volts_from_1_to_the_box_s_max(page):
    """(b) The same rule as the sidebar's box (app-wiring _wirePowerPanel):
    whole volts, 1 or more, up to the box's max of 1000 (index.html). A
    fraction (120.5), 0, a negative figure, text or 100000 is refused on
    change - the figure in force goes back in the box - and never stored;
    121 and 1000 are accepted and become the figure in force."""
    pg, ids = page
    saved = pg.evaluate("() => window.app.getPreferences()")
    assert pg.evaluate("() => document.getElementById('pref-power-voltage-custom').getAttribute('max')") == '1000'
    try:
        pg.evaluate(SET_PREFS_JS, {'powerVoltage': 208, 'breakoutType': 'soca-true1'})
        _open(pg)
        _tab(pg, 'power')
        _set(pg, 'pref-power-voltage-select', 'custom')
        for bad in ('120.5', '0', '-5', 'abc', '1e-9', '100000', '1000.5'):
            st = _box(pg, bad)
            assert st['box'] == '208' and st['gate'] == 208 and st['read'][0] == 208, (bad, st)
        st = _box(pg, '121')
        assert st['box'] == '121' and st['gate'] == 121 and st['read'][0] == 121, st
        st = _box(pg, '120.5')
        assert st['box'] == '121' and st['read'][0] == 121, st
        st = _box(pg, '1000')
        assert st['box'] == '1000' and st['gate'] == 1000, st
        st = _box(pg, '1001')
        assert st['box'] == '1000' and st['gate'] == 1000, st
        _box(pg, '100000')
        _save(pg)
        served = _served(pg)
        assert served['powerVoltage'] == 1000, served
    finally:
        _restore_voltage_prefs(pg, saved)
    assert ids['errors'] == [], ids['errors']


def test_a_custom_voltage_typed_digit_by_digit_keeps_the_breakout_pick(page):
    """(c) Typing 208 into the custom box re-gated on every keystroke - at
    2 V, then 20 V - and the L21-30 pick snapped to Edison on the first key
    and never came back. Now the box commits on change / blur only, and
    the user's pick is remembered: it comes back whenever the voltage
    allows it again, and a new pick replaces it."""
    pg, ids = page
    saved = pg.evaluate("() => window.app.getPreferences()")
    try:
        pg.evaluate(SET_PREFS_JS, {'powerVoltage': 208, 'breakoutType': 'soca-true1'})
        _open(pg)
        _tab(pg, 'power')
        _set(pg, 'pref-breakout-type', 'l2130-true1')
        _set(pg, 'pref-power-voltage-select', 'custom')
        assert pg.evaluate(VOLTAGE_UI_JS)['box'] == '208'
        # keystrokes: nothing gates, the pick stands
        for partial in ('1', '11', '110'):
            st = _box(pg, partial, event='input')
            assert st['breakout'] == 'l2130-true1', (partial, st)
        # the change at 110: the pick cannot run, the class default is shown
        st = _box(pg, '110')
        assert st['breakout'] == 'soca-edison' and st['gate'] == 110, st
        assert 'l2130-true1' in st['greyed'], st
        assert st['read'] == [110, 'soca-edison'], st
        # 208 again: the pick is back
        for partial in ('2', '20'):
            st = _box(pg, partial, event='input')
            assert st['breakout'] == 'soca-edison', (partial, st)
        st = _box(pg, '208')
        assert st['breakout'] == 'l2130-true1' and st['read'] == [208, 'l2130-true1'], st
        # a new pick replaces the remembered one
        _set(pg, 'pref-breakout-type', 'soca-powercon')
        st = _box(pg, '110')
        assert st['breakout'] == 'soca-powercon', st
        st = _box(pg, '208')
        assert st['breakout'] == 'soca-powercon', st
        _save(pg)
        served = _served(pg)
        assert (served['powerVoltage'], served['breakoutType']) == (208, 'soca-powercon'), served
        # the stored pair is the pick on the next open, and a voltage the
        # stored pick cannot run snaps it, a voltage that can brings it back
        pg.evaluate(SET_PREFS_JS, {'powerVoltage': 208, 'breakoutType': 'l2130-powercon'})
        _open(pg)
        _tab(pg, 'power')
        _set(pg, 'pref-power-voltage-select', '110')
        assert pg.evaluate(VOLTAGE_UI_JS)['breakout'] == 'soca-edison'
        _set(pg, 'pref-power-voltage-select', '208')
        assert pg.evaluate(VOLTAGE_UI_JS)['breakout'] == 'l2130-powercon'
        pg.locator('#preferences-cancel').click()
        pg.wait_for_timeout(200)
    finally:
        _restore_voltage_prefs(pg, saved)
    assert ids['errors'] == [], ids['errors']
