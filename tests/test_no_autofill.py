"""No browser or OS autofill ever changes a show, on any field.

"i just had autofill change a bunch of stuff. this cannot happen."
(owner, 2026-11-05)

With the Export window open the owner typed in the Project Manager field,
and the browser's contact AutoFill filled that field, a multi name in the
folded tray, the Designer and the phone inside a second. The app saw an
`input` and a `change` on each and did what they said: Rename Multi eight
times across screens, Set Binder Designer, the phone, undone by hand.

The rule lives in one place, helpers.js installFieldGuard, installed first
thing by main.js. Every field gets the no-fill hints as it appears, and one
capture listener on the window refuses a value that neither page script nor
the person's own typing put there. BURST_JS replays the log: the value is
written past the page's script, the way the browser's native code writes it
(a fresh frame's own setter is the one road to that from a test), then the
same two events fire on a field that does not have focus.

Run locally (each session takes its own free port, so it runs beside
any other):
    python -m pytest tests/test_no_autofill.py -v --browser chromium
    python -m pytest tests/test_no_autofill.py -v --browser firefox
"""

import json
import os
import re
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


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
        return fh.read()


def _js_sources():
    folder = os.path.join(ROOT, 'src', 'static', 'js')
    for name in sorted(os.listdir(folder)):
        if name.endswith('.js') and name != 'socket.io.min.js':
            yield name, _src('src', 'static', 'js', name)


# ── the wiring (new files must not rot) ──────────────────────────────────

def test_the_guard_is_installed_before_anything_writes_a_field():
    main = _src('src', 'static', 'js', 'main.js')
    helpers = _src('src', 'static', 'js', 'helpers.js')
    assert re.search(r'export \{[^}]*\binstallFieldGuard\b', helpers)
    assert 'installFieldGuard' in main.split("document.addEventListener('DOMContentLoaded'")[0]
    assert main.index('installFieldGuard(document);') < main.index('new LEDRasterApp()')
    assert main.index('installFieldGuard(document);') < main.index('registerGlobalClientLogging();')
    body = helpers[helpers.index('function installFieldGuard(doc)'):]
    body = body[:body.index('\n}\n')]
    # Capture on the window: ahead of every listener in the app, the
    # change log among them, so a refused value is never written anywhere.
    assert "win.addEventListener('input', guard, true);" in body
    assert "win.addEventListener('change', guard, true);" in body


def test_no_field_can_sit_where_the_document_pass_cannot_reach():
    """The pass walks one document. A shadow root or a frame would hide a
    field from it, so the app has neither; a window of its own would be a
    document with no guard."""
    template = _src('src', 'templates', 'index.html')
    assert '<iframe' not in template
    for name, text in _js_sources():
        assert 'attachShadow' not in text, name
        assert "createElement('iframe')" not in text, name
        assert '<iframe' not in text, name
        hits = re.findall(r"window\.open\([^)]*\)", text)
        for hit in hits:
            assert 'noopener' in hit, f'{name}: {hit} opens a window the page can write to'


def test_no_text_field_carries_a_name_for_the_heuristics_to_read():
    """A dash in a `name` is reported to turn a field into a phone box in
    the contact fill, past autocomplete="off". The text fields have none;
    only the radio groups use `name`."""
    template = _src('src', 'templates', 'index.html')
    for tag in re.findall(r'<(?:input|textarea|select)\b[^>]*>', template):
        if re.search(r'\sname="', tag):
            assert re.search(r'type="(radio|checkbox)"', tag), tag


# ── the browser ───────────────────────────────────────────────────────────

SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = []; proj.beaches = [];
    proj.name = 'Fill Seed';
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
    app.dedupeProjectLayers('no_autofill_setup');
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
    app.resetHistory('Fill Seed');
    return {id: wall.id, distroId: d.id};
}"""

# Beacons are the only way out of sendClientLog, so they are read at the
# source. The frame's setters are the native ones, past the page's script.
HARNESS_JS = """
window.__logs = [];
navigator.sendBeacon = (url, blob) => {
    blob.text().then(t => window.__logs.push(JSON.parse(t)));
    return true;
};
"""

BURST_JS = """() => {
    if (window.__frame) return;
    const frame = document.createElement('iframe');
    frame.style.display = 'none';
    document.body.appendChild(frame);
    window.__frame = frame.contentWindow;
    window.__fill = (el, value) => {
        const w = window.__frame;
        const type = {INPUT: w.HTMLInputElement, TEXTAREA: w.HTMLTextAreaElement,
                      SELECT: w.HTMLSelectElement}[el.tagName];
        Object.getOwnPropertyDescriptor(type.prototype, 'value').set.call(el, value);
    };
    window.__burst = (el, value) => {
        window.__fill(el, value);
        el.dispatchEvent(new Event('input', {bubbles: true, composed: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    };
    window.__field = (key) => document.getElementById(key)
        || document.querySelector(`[data-lrd-field="${key}"]`);
    window.__reached = [];
    document.addEventListener('input', (e) => window.__reached.push(['input', e.target.id]));
    document.addEventListener('change', (e) => window.__reached.push(['change', e.target.id]));
}"""

SNAPSHOT_JS = """async () => {
    const app = window.app;
    return {
        project: JSON.stringify(app.project),
        served: JSON.stringify(await (await fetch('/api/project')).json()),
        prefs: JSON.stringify(await (await fetch('/api/preferences')).json()),
        history: app.history.length,
        index: app.historyIndex,
        action: app.history[app.historyIndex] ? app.history[app.historyIndex].action : null,
    };
}"""

# Everything the log's burst hit, and every other project field the Export
# window saves live, and a project field outside it.
NAME = 'Test Person'
PHONE = '555 0100'


def _burst_fields(wall_id):
    return [
        ('export-binder-pm-name', NAME),
        (f'power-soca-name-{wall_id}-1', NAME),
        ('export-binder-designer', NAME),
        ('export-binder-pm-phone', PHONE),
        ('export-binder-pm-email', 'test@example.com'),
        ('export-binder-venue', NAME),
        ('export-binder-dates', NAME),
        ('export-binder-drafter', NAME),
        ('export-binder-engineer', NAME),
        ('export-binder-rev', '9'),
        ('project-name', NAME),
        ('project-notes', NAME),
    ]


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(HARNESS_JS)
    pg = context.new_page()
    errors, writes = [], []
    pg.on('pageerror', lambda e: errors.append(str(e)))

    def note(req):
        if '/api/' in req.url and req.method != 'GET' and '/api/log' not in req.url:
            writes.append(f'{req.method} {req.url}')
    pg.on('request', note)
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(400)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(1000)
    pg.evaluate(BURST_JS)
    ids['errors'] = errors
    ids['writes'] = writes
    yield pg, ids
    context.close()


@pytest.fixture(autouse=True)
def _windows_closed(request):
    """A test that stops early leaves no window over the next one."""
    yield
    if 'page' in request.fixturenames:
        pg, _ids = request.getfixturevalue('page')
        pg.evaluate("""() => {
            for (const id of ['export-modal', 'preferences-modal', 'pull-sheet-modal']) {
                const m = document.getElementById(id);
                if (m) m.style.display = 'none';
            }
            const a = document.activeElement;
            if (a && a.blur) a.blur();
        }""")


def _blur_all(pg):
    pg.evaluate("() => { const a = document.activeElement; if (a && a.blur) a.blur(); }")
    pg.wait_for_timeout(100)


def _open_binder(pg):
    pg.evaluate("() => window.app.openExportModal('binder')")
    pg.wait_for_timeout(500)


def _close_export(pg):
    pg.evaluate("""() => {
        const m = document.getElementById('export-modal');
        if (m) m.style.display = 'none';
    }""")
    _blur_all(pg)


def _settled(pg):
    """Long enough for any debounced save a handler could have queued."""
    pg.wait_for_timeout(1500)


def _reached(pg):
    return pg.evaluate("() => window.__reached.splice(0)")


def _logs(pg, action):
    pg.wait_for_timeout(200)
    return [entry for entry in pg.evaluate("() => window.__logs")
            if entry['action'] == action]


def _clear_logs(pg):
    pg.evaluate("() => { window.__logs.length = 0; window.__reached.length = 0; }")


# ── every field is covered ────────────────────────────────────────────────

MISSING_JS = """() => {
    const notText = new Set(['checkbox', 'radio', 'range', 'color', 'file', 'button',
                             'submit', 'reset', 'image', 'hidden']);
    const fields = [...document.querySelectorAll('input, textarea, select')]
        .filter(el => el.tagName !== 'INPUT' || !notText.has(el.type));
    const hints = {'autocomplete': 'off', 'data-form-type': 'other', 'data-lpignore': 'true',
                   'data-1p-ignore': 'true', 'data-bwignore': 'true'};
    const bare = fields.filter(el => Object.entries(hints)
        .some(([k, v]) => el.getAttribute(k) !== v));
    return {count: fields.length,
            bare: bare.map(el => el.id || el.dataset.lrdField || el.className || el.outerHTML)};
}"""


def test_every_field_the_app_builds_carries_the_hints(page):
    pg, ids = page
    seen = 0
    for mode in ('pixel-map', 'cabinet-id', 'data-flow', 'power'):
        pg.locator(f'[data-mode="{mode}"]').click()
        pg.wait_for_timeout(300)
        got = pg.evaluate(MISSING_JS)
        assert not got['bare'], f'{mode}: {got["bare"]}'
        seen = max(seen, got['count'])
    assert seen > 100, f'the sweep looked at {seen} fields: is it looking at the app?'
    # JS-built fields, each window as it opens: Preferences, the name prompt
    # the app asks with, the pull sheet editor's cells, a rename in the list.
    pg.evaluate("() => window.app.openPreferencesModal()")
    pg.wait_for_timeout(500)
    assert pg.evaluate(MISSING_JS)['bare'] == []
    pg.evaluate("""() => { const m = document.getElementById('preferences-modal');
                           if (m) m.style.display = 'none'; }""")
    pg.evaluate("() => { window.app.openPullSheetEditor({}); }")
    pg.wait_for_timeout(1200)
    got = pg.evaluate(MISSING_JS)
    assert got['bare'] == []
    assert pg.evaluate("() => document.querySelectorAll('.pull-cell').length") > 0
    pg.evaluate("""() => { const m = document.getElementById('pull-sheet-modal');
                           if (m) m.style.display = 'none'; }""")


def test_a_field_nobody_has_written_yet_is_covered_when_it_appears(page):
    """The new field of next year: built by a script, deep in a block,
    asking for autocomplete, with nothing done for it."""
    pg, ids = page
    _clear_logs(pg)
    got = pg.evaluate("""async () => {
        const box = document.createElement('div');
        box.id = 'fill-new-block';
        box.innerHTML = '<div><input id="fill-new-text" autocomplete="on" placeholder="Name">'
            + '<textarea id="fill-new-area"></textarea>'
            + '<select id="fill-new-pick"><option>a</option><option>b</option></select></div>';
        document.body.appendChild(box);
        await new Promise(r => setTimeout(r, 0));
        const text = document.getElementById('fill-new-text');
        const attrs = ['fill-new-text', 'fill-new-area', 'fill-new-pick'].map(
            id => document.getElementById(id).getAttribute('autocomplete'));
        window.__burst(text, 'Test Person');
        window.__burst(document.getElementById('fill-new-area'), 'Test Person');
        const out = {attrs, text: text.value,
                     area: document.getElementById('fill-new-area').value,
                     reached: window.__reached.length};
        box.remove();
        return out;
    }""")
    assert got == {'attrs': ['off', 'off', 'off'], 'text': '', 'area': '', 'reached': 0}
    ids_logged = {e['details']['id'] for e in _logs(pg, 'autofill_refused')}
    assert ids_logged == {'fill-new-text', 'fill-new-area'}


# ── the log's burst, replayed ─────────────────────────────────────────────

def test_the_burst_from_the_log_writes_nothing_anywhere(page):
    pg, ids = page
    _open_binder(pg)
    _clear_logs(pg)
    fields = [(key, value) for key, value in _burst_fields(ids['id'])
              if key != 'export-binder-pm-name']
    keys = [key for key, _ in fields]
    missing = pg.evaluate("(keys) => keys.filter(k => !window.__field(k))", keys)
    assert not missing, f'not in the page: {missing}'
    shown = pg.evaluate("(keys) => keys.map(k => window.__field(k).value)", keys)
    before = pg.evaluate(SNAPSHOT_JS)
    ids['writes'].clear()

    # Same order as the log, one task, on fields without focus.
    pg.evaluate("""(fields) => {
        for (const [key, value] of fields) window.__burst(window.__field(key), value);
    }""", fields)
    _settled(pg)

    after = pg.evaluate(SNAPSHOT_JS)
    assert after['project'] == before['project'], 'the show in memory changed'
    assert after['served'] == before['served'], 'the served show changed'
    assert after['prefs'] == before['prefs'], 'a preference changed'
    assert (after['history'], after['index']) == (before['history'], before['index']), (
        f'a history step was made: {before["action"]} -> {after["action"]}')
    assert ids['writes'] == [], f'a save went out: {ids["writes"]}'
    assert pg.evaluate("(keys) => keys.map(k => window.__field(k).value)", keys) == shown, (
        'a field kept what the fill put in it')
    assert _reached(pg) == [], 'an event reached the app'
    assert _logs(pg, 'ui_change') == [], 'the filled value went to the log'

    refused = _logs(pg, 'autofill_refused')
    assert [e['details']['id'] for e in refused] == keys, 'one line per field, in order'
    for entry in refused:
        assert entry['details']['reason'] == 'not_focused'
        assert entry['details']['event'] == 'input'
    text = json.dumps(refused)
    assert NAME not in text and PHONE not in text, 'the log never carries the value'
    assert ids['errors'] == []
    _close_export(pg)


def test_the_field_being_typed_in_keeps_its_typing(page):
    """The reported field: it has focus, and the fill hits it too. A fill
    is a plain `input` event and a `change` with the caret still there,
    which typing never is, so the text typed so far stays and commits."""
    pg, ids = page
    _open_binder(pg)
    pm = pg.locator('#export-binder-pm-name')
    pm.fill('')
    pm.press('Tab')
    _clear_logs(pg)
    pm.click()
    pg.keyboard.type('Pa')
    assert pg.evaluate("() => document.activeElement.id") == 'export-binder-pm-name'
    before = pg.evaluate(SNAPSHOT_JS)
    ids['writes'].clear()
    pg.evaluate("(v) => window.__burst(document.getElementById('export-binder-pm-name'), v)", NAME)
    _settled(pg)
    after = pg.evaluate(SNAPSHOT_JS)
    assert pm.input_value() == 'Pa'
    assert after['project'] == before['project'] and after['index'] == before['index']
    assert ids['writes'] == []
    refused = _logs(pg, 'autofill_refused')
    assert [(e['details']['id'], e['details']['reason'], e['details']['focused'])
            for e in refused] == [('export-binder-pm-name', 'not_typed', True)]
    # The caret is still in the field and the edit carries on as normal.
    pg.keyboard.type('t')
    pg.keyboard.press('Tab')
    pg.wait_for_timeout(300)
    assert pg.evaluate(
        "() => window.app.project.binder.projectManager.name") == 'Pat'
    assert pg.evaluate(SNAPSHOT_JS)['action'] == 'Set Binder Project Manager'
    _close_export(pg)


def test_a_change_alone_is_refused_too(page):
    pg, ids = page
    _open_binder(pg)
    _clear_logs(pg)
    index = pg.evaluate("() => window.app.historyIndex")
    was = pg.evaluate("""(v) => {
        const el = document.getElementById('export-binder-designer');
        const was = el.value;
        window.__fill(el, v);
        el.dispatchEvent(new Event('change', {bubbles: true}));
        return was;
    }""", NAME)
    _settled(pg)
    assert pg.input_value('#export-binder-designer') == was
    assert pg.evaluate("() => window.app.historyIndex") == index
    assert len(_logs(pg, 'autofill_refused')) == 1
    _close_export(pg)


def test_a_second_fill_of_a_refused_field_is_refused_too(page):
    pg, ids = page
    _open_binder(pg)
    index = pg.evaluate("() => window.app.historyIndex")
    was = pg.input_value('#export-binder-venue')
    for _ in range(3):
        pg.evaluate("(v) => window.__burst(document.getElementById('export-binder-venue'), v)", NAME)
    _settled(pg)
    assert pg.input_value('#export-binder-venue') == was
    assert pg.evaluate("() => window.app.historyIndex") == index
    _close_export(pg)


def test_a_select_nobody_touched_is_put_back_and_one_pressed_is_not(page):
    """Selects fire plain events however they change, and WebKit on the Mac
    gives a clicked select no focus, so the press is what counts. The live
    flag turns off the allowance for the automated browser's own
    select_option."""
    pg, ids = page
    _blur_all(pg)
    _clear_logs(pg)
    got = pg.evaluate("""() => {
        window.__lrdFieldGuardLive = true;
        const sel = document.getElementById('power-jump-unit');
        const was = sel.value;
        const other = [...sel.options].map(o => o.value).find(v => v !== was);
        window.__burst(sel, other);
        const refused = sel.value;
        const reachedRefused = window.__reached.length;
        sel.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
        window.__burst(sel, other);
        const pressed = sel.value;
        const reachedPressed = window.__reached.length;
        // Put it back the way a script does, which is always allowed.
        sel.value = was;
        sel.dispatchEvent(new Event('change', {bubbles: true}));
        delete window.__lrdFieldGuardLive;
        document.body.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
        return {was, other, refused, reachedRefused, pressed, reachedPressed};
    }""")
    assert got['refused'] == got['was'] and got['reachedRefused'] == 0, got
    assert got['pressed'] == got['other'] and got['reachedPressed'] > 0, got
    _settled(pg)


# ── what must keep working ────────────────────────────────────────────────

def test_real_typing_commits_on_tab_and_enter(page):
    pg, ids = page
    _open_binder(pg)
    venue = pg.locator('#export-binder-venue')
    venue.click()
    venue.press('ControlOrMeta+a')
    pg.keyboard.type('Main Hall')
    pg.keyboard.press('Tab')
    pg.wait_for_timeout(200)
    assert pg.evaluate("() => window.app.project.binder.venue") == 'Main Hall'
    assert pg.evaluate("() => document.activeElement.id") != 'export-binder-venue', (
        'Tab moves on')
    venue.click()
    venue.press('ControlOrMeta+a')
    pg.keyboard.type('Side Hall')
    pg.keyboard.press('Enter')
    pg.wait_for_timeout(200)
    assert pg.evaluate("() => window.app.project.binder.venue") == 'Side Hall'
    assert pg.evaluate("() => document.activeElement.id") != 'export-binder-venue', (
        'Enter lets go')
    _close_export(pg)


def test_playwright_fill_and_a_real_paste_reach_the_show(page):
    pg, ids = page
    _open_binder(pg)
    _clear_logs(pg)
    drafter = pg.locator('#export-binder-drafter')
    drafter.fill('Drawn By Fill')
    drafter.press('Tab')
    pg.wait_for_timeout(200)
    assert pg.evaluate("() => window.app.project.binder.drafter") == 'Drawn By Fill'
    # Copy from one field and paste into another with the keyboard: a real
    # insertFromPaste, one jump of many characters.
    drafter.click()
    drafter.press('ControlOrMeta+a')
    drafter.press('ControlOrMeta+c')
    dates = pg.locator('#export-binder-dates')
    dates.click()
    dates.press('ControlOrMeta+a')
    dates.press('ControlOrMeta+v')
    dates.press('Tab')
    pg.wait_for_timeout(200)
    assert pg.evaluate("() => window.app.project.binder.dates") == 'Drawn By Fill'
    assert _logs(pg, 'autofill_refused') == []
    _close_export(pg)


def test_a_number_stepper_a_select_and_a_color_still_commit(page):
    """All three fire plain events, and a stepper's value jumps."""
    pg, ids = page
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    _clear_logs(pg)
    size = pg.locator('#power-label-size')
    size.scroll_into_view_if_needed()
    was = int(size.input_value())
    size.click()
    size.press('ArrowUp')
    size.press('ArrowUp')
    size.press('Tab')
    pg.wait_for_timeout(200)
    assert int(size.input_value()) == was + 2
    assert ['change', 'power-label-size'] in _reached(pg)

    unit = pg.locator('#power-jump-unit')
    start = unit.input_value()
    other = 'm' if start == 'ft' else 'ft'
    unit.select_option(other)
    pg.wait_for_timeout(200)
    assert unit.input_value() == other
    assert ['change', 'power-jump-unit'] in _reached(pg)
    unit.focus()
    pg.keyboard.press('ArrowUp' if start == 'ft' else 'ArrowDown')
    pg.wait_for_timeout(200)
    assert unit.input_value() == start, 'a real key on a focused select'
    assert ['change', 'power-jump-unit'] in _reached(pg)
    _blur_all(pg)

    color = pg.evaluate("""() => {
        const el = document.querySelector('input[type="color"]');
        el.value = '#123456';
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        return el.value;
    }""")
    assert color == '#123456'
    assert _logs(pg, 'autofill_refused') == []


def test_a_script_write_goes_through_on_a_field_without_focus(page):
    """The app's own write and a guide's step are this: a value set by page
    script, then the events, with focus anywhere. The setter saw it."""
    pg, ids = page
    _open_binder(pg)
    _blur_all(pg)
    _clear_logs(pg)
    pg.evaluate("""() => {
        const el = document.getElementById('export-binder-designer');
        el.value = 'Set By Script';
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    pg.wait_for_timeout(200)
    assert pg.evaluate("() => window.app.project.binder.designer") == 'Set By Script'
    assert _logs(pg, 'autofill_refused') == []
    _close_export(pg)


def test_a_script_write_straight_after_a_refusal_is_not_swallowed(page):
    pg, ids = page
    _open_binder(pg)
    _blur_all(pg)
    pg.evaluate("""(v) => {
        const el = document.getElementById('export-binder-designer');
        window.__burst(el, v);
        el.value = 'After The Fill';
        el.dispatchEvent(new Event('change', {bubbles: true}));
    }""", NAME)
    pg.wait_for_timeout(200)
    assert pg.evaluate("() => window.app.project.binder.designer") == 'After The Fill'
    _close_export(pg)


def test_undo_puts_a_value_back_and_the_fill_cannot_undo_that(page):
    pg, ids = page
    _open_binder(pg)
    designer = pg.locator('#export-binder-designer')
    designer.fill('First')
    designer.press('Tab')
    designer.fill('Second')
    designer.press('Tab')
    pg.wait_for_timeout(300)
    pg.evaluate("() => window.app.undo()")
    pg.wait_for_timeout(600)
    assert pg.evaluate("() => window.app.project.binder.designer") == 'First'
    pg.evaluate("() => window.app.syncBinderControls()")
    assert designer.input_value() == 'First'
    index = pg.evaluate("() => window.app.historyIndex")
    pg.evaluate("(v) => window.__burst(document.getElementById('export-binder-designer'), v)", NAME)
    _settled(pg)
    assert designer.input_value() == 'First', 'put back to the value undo left, not an older one'
    assert pg.evaluate("() => window.app.historyIndex") == index
    _close_export(pg)


def test_a_datalist_pick_is_the_person(page):
    """A pick from the field's own list arrives as a plain `input`, with
    focus, and no key if the mouse chose it. A value not on the list
    arriving the same way is a fill."""
    pg, ids = page
    pg.evaluate("""() => {
        const box = document.createElement('div');
        box.id = 'fill-list-block';
        box.innerHTML = '<input id="fill-list" list="fill-list-options">'
            + '<datalist id="fill-list-options"><option value="Rigger"></datalist>';
        document.body.appendChild(box);
    }""")
    _clear_logs(pg)
    got = pg.evaluate("""() => {
        const el = document.getElementById('fill-list');
        el.focus();
        window.__burst(el, 'Rigger');
        const picked = el.value;
        window.__burst(el, 'Test Person');
        const filled = el.value;
        el.blur();
        document.getElementById('fill-list-block').remove();
        return {picked, filled};
    }""")
    assert got == {'picked': 'Rigger', 'filled': 'Rigger'}


def test_a_field_rebuilt_under_the_tray_is_known_from_its_first_value(page):
    """The multi name is rebuilt with each tray render: a fill after a
    rebuild puts back the current name, not an old node's."""
    pg, ids = page
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(300)
    key = f"power-soca-name-{ids['id']}-1"
    pg.evaluate("""(key) => {
        const el = window.__field(key);
        el.value = 'Stage Left';
        el.dispatchEvent(new Event('change', {bubbles: true}));
    }""", key)
    pg.wait_for_timeout(500)
    assert pg.evaluate("(key) => window.__field(key).value", key) == 'Stage Left'
    index = pg.evaluate("() => window.app.historyIndex")
    pg.evaluate("([key, v]) => window.__burst(window.__field(key), v)", [key, NAME])
    _settled(pg)
    assert pg.evaluate("(key) => window.__field(key).value", key) == 'Stage Left'
    assert pg.evaluate("() => window.app.historyIndex") == index
    assert pg.evaluate(
        "() => window.app.project.layers[0].powerSocaNames['1']") == 'Stage Left'
