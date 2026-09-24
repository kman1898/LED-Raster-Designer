"""Enter ends the edit, in every single-line field.

"one thing that's been an issue since day 1 is when I type into say the
project name text box and finish typing, when I hit enter it doesn't
complete the process. It doesn't until I click out of the box. So we need
to audit that and make sure it doesn't happen there or anywhere else. But
in other areas if I don't hit enter I still like being able to tab to the
next one." (owner, 2026-09-24)

Enter already fired `change` in a text or number field, so a field that
commits on change had saved - but it kept the caret and looked unfinished,
and a field that commits on blur got nothing. The rule, in one place
(helpers.js installEnterEndsEdit, installed by app-core.js
setupEventListeners): a plain Enter in a single-line field lets go of it,
one tick later, from a document-level BUBBLE listener - so a field with its
own Enter handler runs first and keeps its own rule by preventDefault /
stopPropagation. Tab, Shift+Enter, a textarea's newline, a field its own
handler flagged `invalid` and an Enter that picked a datalist suggestion
are left alone.

Run locally (each session takes its own free port, so it runs beside
any other):
    python3 -m pytest tests/test_enter_ends_the_edit.py -v --browser chromium
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── the wiring (new files must not rot) ──────────────────────────────────

def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
        return fh.read()


def test_the_rule_is_one_bubble_listener_installed_at_start():
    helpers = _src('src', 'static', 'js', 'helpers.js')
    core = _src('src', 'static', 'js', 'app-core.js')
    assert 'function installEnterEndsEdit(doc)' in helpers
    assert 'installEnterEndsEdit };' in helpers, 'the helper is exported'
    # Bubble phase: the listener takes no third (capture) argument, so a
    # field's own Enter handler runs first and can opt out.
    body = helpers[helpers.index('function installEnterEndsEdit(doc)'):]
    body = body[:body.index('\n}\n')]
    assert "doc.addEventListener('keydown', (e) => {" in body
    assert '}, true);' not in body and '{ capture: true }' not in body
    assert 'e.defaultPrevented' in body
    assert 'installEnterEndsEdit(document);' in core
    assert 'installEnterEndsEdit' in core.split('\n')[2], 'imported from helpers.js'


# ── the browser ───────────────────────────────────────────────────────────

# One screen WALL with a distro SR feeding its first multi: a Screen Info
# field, the power sidebar, a tray name, a cable sheet and a pull sheet
# all have something to show.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    proj.name = 'Enter Seed';
    delete proj.port_assignments; delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'WALL', columns: 8, rows: 12,
        cabinet_width: 200, cabinet_height: 200});
    const p1 = await j('GET', '/api/project');
    for (const l of p1.layers) {
        await j('PUT', `/api/layer/${l.id}`, {powerVoltage: 208, powerAmperage: 10,
            panelWatts: 200, processorType: 'novastar-coex-1g'});
    }
    const app = window.app;
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('enter_ends_edit_setup');
    const wall = app.project.layers[0];
    app.selectLayer(wall);
    const d = app.addDistro({name: 'SR'});
    app.setSocaDistro(wall, 1, d.id);
    app.setSocaNumber(wall, 1, 1);
    await app.refreshProcessors();
    app.renderLayers();
    app._circuitTailCache = null;
    app.renderHardwareDock();
    document.getElementById('project-name').value = app.project.name;
    app.resetHistory('Enter Seed');
    return {id: wall.id, distroId: d.id};
}"""

# Where focus is, and the undo log's tail.
STATE_JS = """() => {
    const a = document.activeElement;
    const app = window.app;
    return {
        focus: a ? (a.id || (a.dataset && a.dataset.lrdField) || a.tagName) : null,
        body: a === document.body || a === null,
        action: app.history[app.historyIndex] ? app.history[app.historyIndex].action : null,
        index: app.historyIndex,
    };
}"""

# Whether the last keydown reached the end of its bubble path with the
# default prevented - i.e. a field's own Enter handler took it.
PROBE_JS = """() => {
    if (window.__enterProbe) return;
    window.__enterProbe = {prevented: null, reachedWindow: false};
    window.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        window.__enterProbe.prevented = e.defaultPrevented;
        window.__enterProbe.reachedWindow = true;
    });
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
    pg.wait_for_timeout(1000)
    pg.evaluate(PROBE_JS)
    ids['errors'] = errors
    yield pg, ids
    context.close()


def _state(pg):
    return pg.evaluate(STATE_JS)


def _served(pg, js, want, timeout_ms=4000):
    waited, got = 0, None
    while waited <= timeout_ms:
        got = pg.evaluate(js)
        if want(got):
            return got
        pg.wait_for_timeout(200)
        waited += 200
    return got


def _mode(pg, mode):
    pg.locator(f'[data-mode="{mode}"]').click()
    pg.wait_for_timeout(400)


def _blur_all(pg):
    pg.evaluate("() => { const a = document.activeElement; if (a && a.blur) a.blur(); }")
    pg.wait_for_timeout(100)


# ── the project name: the reported case ─────────────────────────────────

def test_enter_in_the_project_name_saves_it_and_lets_go(page):
    pg, ids = page
    _blur_all(pg)
    before = _state(pg)
    box = pg.locator('#project-name')
    box.click()
    box.fill('Arena Tour')
    box.press('Enter')
    pg.wait_for_timeout(300)
    st = _state(pg)
    assert st['focus'] != 'project-name', f'the box kept the caret after Enter: {st}'
    assert st['body'], st
    assert pg.evaluate("() => window.app.project.name") == 'Arena Tour'
    assert st['action'] == 'Rename Project' and st['index'] == before['index'] + 1, (
        f'one Rename Project entry, no more: {before} -> {st}')
    served = _served(pg, "async () => (await (await fetch('/api/project')).json()).name",
                     lambda n: n == 'Arena Tour')
    assert served == 'Arena Tour', f'the server has {served!r}'


def test_tab_from_the_project_name_still_moves_on_and_commits(page):
    pg, ids = page
    _blur_all(pg)
    before = _state(pg)
    box = pg.locator('#project-name')
    box.click()
    box.fill('Arena Tour B')
    # The next tab stop, as the page's own order has it.
    box.press('Tab')
    pg.wait_for_timeout(300)
    st = _state(pg)
    assert not st['body'] and st['focus'] != 'project-name', (
        f'Tab must move focus on to the next field, not drop it: {st}')
    assert pg.evaluate("() => window.app.project.name") == 'Arena Tour B'
    assert st['action'] == 'Rename Project' and st['index'] == before['index'] + 1, st
    _blur_all(pg)


def test_shift_enter_does_not_let_go(page):
    pg, ids = page
    box = pg.locator('#project-name')
    box.click()
    box.fill('Arena Tour C')
    box.press('Shift+Enter')
    pg.wait_for_timeout(300)
    assert _state(pg)['focus'] == 'project-name', 'Shift+Enter must leave the caret'
    _blur_all(pg)


# ── one field per audited area ──────────────────────────────────────────

def _cols_read(pg, ids):
    return pg.evaluate("() => window.app.currentLayer.columns")


def _voltage_setup(pg, ids):
    _mode(pg, 'power')
    pg.select_option('#power-voltage-select', 'custom')
    pg.wait_for_timeout(200)


def _pref_setup(pg, ids):
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_timeout(300)
    pg.locator('#preferences-modal .pm-tabstrip [data-key="binder"]').click()
    pg.wait_for_timeout(200)


def _pref_teardown(pg, ids):
    pg.locator('#preferences-save').click()
    pg.wait_for_timeout(300)


def _pref_read(pg, ids):
    return pg.evaluate("() => window.app.getPreferences().binderDrafter")


def _power(pg, ids):
    _mode(pg, 'power')


def _sheet_setup(pg, ids):
    _mode(pg, 'power')
    open_ = pg.evaluate("""(d) => !!document.querySelector(
        `[data-lrd-sec="hwdock-multi-${d}-1"]`).parentElement.querySelector('.hw-dock-cablesheet')""",
        ids['distroId'])
    if not open_:
        pg.locator(f'[data-lrd-field="power-cable-sheet-{ids["distroId"]}-1"]').click()
        pg.wait_for_timeout(500)


def _sheet_teardown(pg, ids):
    pg.locator(f'[data-lrd-field="power-cable-sheet-{ids["distroId"]}-1"]').click()
    pg.wait_for_timeout(300)


# name, setup, selector (formatted with ids), typed value, read-back, expected
AREAS = {
    'screen-info-columns': dict(
        setup=lambda pg, ids: _mode(pg, 'pixel-map'),
        sel='#screen-columns', value='6',
        read=lambda pg, ids: pg.evaluate("() => window.app.currentLayer.columns"),
        want=6),
    'custom-voltage': dict(
        setup=_voltage_setup, sel='#power-voltage-custom', value='240',
        read=lambda pg, ids: pg.evaluate("() => window.app.currentLayer.powerVoltage"),
        want=240),
    'preferences-text': dict(
        # A preference is read on Save: the field lets go and Save keeps it.
        setup=_pref_setup, commit=_pref_teardown,
        sel='#pref-binder-drafter', value='J. Drafter',
        read=_pref_read, want='J. Drafter'),
    'export-binder-venue': dict(
        setup=lambda pg, ids: pg.evaluate("""() => {
            document.getElementById('export-modal').style.display = 'flex';
            const f = document.getElementById('export-format');
            f.value = 'binder';
            f.dispatchEvent(new Event('change'));
        }"""),
        teardown=lambda pg, ids: pg.evaluate(
            "() => { document.getElementById('export-modal').style.display = 'none'; }"),
        sel='#export-binder-venue', value='Red Rocks',
        read=lambda pg, ids: pg.evaluate(
            "() => JSON.stringify(window.app.project.binder || {})"),
        want=lambda v: 'Red Rocks' in v),
    'tray-distro-name': dict(
        setup=_power, sel='[data-lrd-field="distro-name-{distroId}"]', value='SL',
        read=lambda pg, ids: pg.evaluate(
            "(d) => window.app.getDistros().find(x => x.id === d).name", ids['distroId']),
        want='SL'),
    'cable-sheet-length': dict(
        setup=_sheet_setup, teardown=_sheet_teardown,
        sel='[data-lrd-field="power-cable-ft-{id}-1"]', value='25',
        read=lambda pg, ids: pg.evaluate(
            "(id) => ((window.app.project.layers.find(l => l.id === id)"
            ".powerCircuitCables || {})[1] || {}).ft", ids['id']),
        want=25),
}


@pytest.mark.parametrize('area', list(AREAS))
def test_enter_commits_and_lets_go_in_every_area(page, area):
    pg, ids = page
    spec = AREAS[area]
    _blur_all(pg)
    spec['setup'](pg, ids)
    try:
        sel = spec['sel'].format(**ids)
        field = pg.locator(sel)
        field.click()
        field.fill(spec['value'])
        pg.evaluate("() => { window.__enterProbe.prevented = null; }")
        field.press('Enter')
        pg.wait_for_timeout(400)
        st = _state(pg)
        if spec.get('commit'):
            spec['commit'](pg, ids)
        key = sel.lstrip('#')
        assert st['focus'] not in (key, sel), f'{area}: the field kept the caret: {st}'
        # the rule, not a field's own handler, let go of it
        assert pg.evaluate("() => window.__enterProbe.prevented") is False, area
        got = spec['read'](pg, ids)
        want = spec['want']
        if callable(want):
            assert want(got), f'{area}: not committed: {got!r}'
        else:
            assert got == want, f'{area}: not committed: {got!r} != {want!r}'
    finally:
        if spec.get('teardown'):
            spec['teardown'](pg, ids)
        _blur_all(pg)


def test_a_value_the_field_refuses_keeps_the_caret(page):
    """The watts field flags a value it cannot read (.invalid) on the
    change Enter fires: the caret stays so it can be fixed; a good value
    then lets go (test_browser_flows test_invalid_watts_cue_shows_while_focused
    is the cue half of this)."""
    pg, ids = page
    _mode(pg, 'power')
    field = pg.locator('#power-panel-watts')
    field.click()
    field.fill('not a number')
    field.press('Enter')
    pg.wait_for_timeout(300)
    assert _state(pg)['focus'] == 'power-panel-watts'
    field.fill('200')
    field.press('Enter')
    pg.wait_for_timeout(300)
    assert _state(pg)['focus'] != 'power-panel-watts'


def test_an_enter_that_picks_a_suggestion_keeps_the_field(page):
    """A field with a datalist (the fiber type in a box's gear, the pull
    sheet's added-row pickers): WebKit delivers the Enter keydown and THEN
    puts the highlighted suggestion in the box (an `input`, then `change`),
    a moment after the next tick but before the key comes up. An Enter
    that brought a pick chose an option, so the field stays; the next
    Enter ends the edit. The pick is stood in for by a listener at the end
    of the keydown's path (window) writing the suggestion and firing
    `input` - after the document rule has seen the key, as WebKit's does."""
    pg, ids = page
    _blur_all(pg)
    pg.evaluate("""() => {
        const wrap = document.createElement('div');
        wrap.id = 'enter-probe-wrap';
        wrap.style.cssText = 'position:fixed;left:300px;top:300px;z-index:99999';
        wrap.innerHTML = '<input id="enter-probe-pick" type="text" list="enter-probe-list">'
            + '<datalist id="enter-probe-list"><option value="12 Tac Fiber"></datalist>';
        document.body.appendChild(wrap);
        const el = document.getElementById('enter-probe-pick');
        window.__pickNext = true;
        // On window, the last stop of the bubble path: the value changes
        // after the document has seen the keydown, as WebKit's pick does.
        window.addEventListener('keydown', (e) => {
            if (e.target === el && e.key === 'Enter' && window.__pickNext) {
                window.__pickNext = false;
                el.value = '12 Tac Fiber';
                el.dispatchEvent(new Event('input', {bubbles: true}));
            }
        });
    }""")
    try:
        field = pg.locator('#enter-probe-pick')
        field.click()
        field.fill('12')
        field.press('Enter')
        pg.wait_for_timeout(200)
        assert _state(pg)['focus'] == 'enter-probe-pick', 'the pick must keep the field'
        assert field.input_value() == '12 Tac Fiber'
        field.press('Enter')
        pg.wait_for_timeout(200)
        assert _state(pg)['focus'] != 'enter-probe-pick', 'the next Enter ends the edit'
    finally:
        pg.evaluate("() => document.getElementById('enter-probe-wrap').remove()")


def test_enter_in_the_notes_is_a_newline(page):
    pg, ids = page
    _blur_all(pg)
    pg.evaluate("""() => {
        const p = document.getElementById('notes-panel');
        if (p && p.classList.contains('collapsed')) document.getElementById('notes-toggle').click();
    }""")
    pg.wait_for_timeout(200)
    notes = pg.locator('#project-notes')
    notes.click()
    notes.fill('')
    notes.type('line one')
    notes.press('Enter')
    notes.type('line two')
    pg.wait_for_timeout(300)
    assert _state(pg)['focus'] == 'project-notes', 'the notes kept focus'
    assert notes.input_value() == 'line one\nline two'
    assert pg.evaluate("() => window.app.project.notes") == 'line one\nline two'
    _blur_all(pg)


# ── fields with their own Enter keep their own rule ─────────────────────

def test_the_screens_panel_rename_keeps_its_own_enter(page):
    """app-layers-panel.js: Enter blurs the name itself and the blur ends
    the edit (read-only again, one Rename Layer)."""
    pg, ids = page
    _mode(pg, 'pixel-map')
    name = pg.locator(f'#layers-list .layer-item[data-layer-id="{ids["id"]}"] .layer-name-input')
    name.dblclick()
    pg.wait_for_timeout(200)
    assert pg.evaluate(f"""() => !document.querySelector(
        '#layers-list .layer-item[data-layer-id="{ids["id"]}"] .layer-name-input').readOnly""")
    before = _state(pg)
    name.fill('MAIN WALL')
    name.press('Enter')
    pg.wait_for_timeout(400)
    st = _state(pg)
    el = pg.evaluate(f"""() => {{
        const el = document.querySelector(
            '#layers-list .layer-item[data-layer-id="{ids["id"]}"] .layer-name-input');
        return {{readOnly: el.readOnly, focused: document.activeElement === el}};
    }}""")
    assert el == {'readOnly': True, 'focused': False}, el
    assert pg.evaluate("() => window.app.currentLayer.name") == 'MAIN WALL'
    assert st['action'] == 'Rename Layer' and st['index'] == before['index'] + 1, st


def test_a_pull_sheet_cell_keeps_its_own_enter(page):
    """app-pull-sheet-editor.js: the board's own Enter handler prevents the
    default and blurs the cell, and the blur's change commits it - the
    document rule stands aside (defaultPrevented)."""
    pg, ids = page
    _mode(pg, 'power')
    pg.evaluate("() => window.app.openPullSheetEditor()")
    pg.wait_for_timeout(600)
    try:
        cell = pg.locator('#pull-sheet-board tr.pull-row input[data-field="notes"]').first
        cell.click()
        cell.fill('bring spares')
        pg.evaluate("() => { window.__enterProbe.prevented = null; }")
        cell.press('Enter')
        pg.wait_for_timeout(400)
        assert pg.evaluate("() => window.__enterProbe.prevented") is True, (
            "the board's own handler no longer takes Enter")
        assert pg.evaluate(
            "() => document.activeElement.classList.contains('pull-cell')") is False
        assert 'bring spares' in pg.evaluate(
            "() => JSON.stringify(window.app.project.pullSheetEdits || {})")
    finally:
        pg.evaluate("() => window.app.closePullSheetEditor()")
        pg.wait_for_timeout(200)


def test_a_cable_sheet_quick_fill_box_keeps_its_own_enter(page):
    """app-dock-cable-sheets.js: Enter in the "any length" box fills and
    stops the key there (preventDefault + stopPropagation) - the document
    rule never sees it."""
    pg, ids = page
    _sheet_setup(pg, ids)
    try:
        box = pg.locator(f'[data-lrd-field="power-cable-fill-any-{ids["distroId"]}-1"]')
        box.click()
        box.fill('12.5')
        pg.evaluate("() => { window.__enterProbe.reachedWindow = false; }")
        box.press('Enter')
        pg.wait_for_timeout(700)
        assert pg.evaluate("() => window.__enterProbe.reachedWindow") is False
        ft = pg.evaluate(
            "(id) => ((window.app.project.layers.find(l => l.id === id)"
            ".powerCircuitCables || {})[1] || {}).ft", ids['id'])
        assert ft == 12.5, ft
    finally:
        _sheet_teardown(pg, ids)
        _blur_all(pg)


def test_no_page_errors(page):
    pg, ids = page
    assert ids['errors'] == [], ids['errors']
