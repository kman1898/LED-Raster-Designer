"""Every guided-tour step acts, and its check says so.

The tours in quickstart.js DEMONSTRATE: each step performs one real action
on a scratch demo show (a ghost cursor travels to the control, the app's own
handlers fire, the result appears) and a check() returns the result note -
or null when the action did not take. This suite drives every tour for
real - startTour(), then #qs-next through every step - and after each act
settles proves two things: the step's anchor resolves and is visible in the
view the step shows it in, and the check returned a note (the callout has a
green .qs-result and no .qs-result-fail). A step whose selector rots or
whose act stops taking fails here with its title.

The engine's contract is pinned too: Back restores the previous step's
entry snapshot and replays its act (no duplicate hardware), Skip puts the
user's own project back deep-equal (history, view, cable-sheet flags and
every transient closed), Escape mid-act never corrupts, and every step's
copy is one action in at most two sentences.

Run locally (each session takes its own free port, so it runs beside
any other):
    python -m pytest tests/test_tour_anchors.py -v --browser chromium
"""

import os
import re
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


# A distinctive project to be put back: two walls on a platform-matched
# processor with a named card, its ports placed on the wall and four of
# them on a snake, plus one 3-phase distro with a multi landed.
SEED_JS = """async () => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await j('PUT', '/api/project', proj);
    await j('POST', '/api/layer/add', {name: 'TOUR WALL', columns: 10, rows: 5,
                                       cabinet_width: 200, cabinet_height: 200});
    await j('POST', '/api/layer/add', {name: 'TOUR WALL B', columns: 4, rows: 4,
                                       cabinet_width: 200, cabinet_height: 200,
                                       offset_x: 2400});
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`,
                 {deviceId: 'novastar-card-h-16xrj45-2xfiber'});
    const cardId = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cardId}`, {name: 'SR'});
    const app = window.app;
    const p1 = await j('GET', '/api/project');
    for (const l of p1.layers) {
        // The H9 is Armor-platform gear; since the platform wall a screen
        // only lands on gear its Processing setting matches.
        await j('PUT', `/api/layer/${l.id}`,
                {powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
                 processorType: 'novastar-armor'});
    }
    const p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('tour_anchor_seed');
    const wall = app.project.layers[0];
    app.selectLayer(wall);
    const d = app.addDistro({name: 'PD'});
    app.setSocaDistro(wall, 1, d.id);
    app.setSocaNumber(wall, 1, 1);
    await app.refreshProcessors();
    await app._assignmentRequest('/api/port-assignments/place-overflow', 'POST',
                                 {layerId: String(wall.id), cardId});
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    const owner = app._dataCableOwner('card', cardId);
    const snakeId = await app.snakePorts(app.snakeMembersOf(owner, [5, 6, 7, 8]), 100);
    await app.refreshProcessors();
    app.renderLayers();
    app.renderHardwareDock();
    app.resetHistory('Tour Anchor Seed');
    return {layerId: wall.id, cardId, snakeId};
}"""

# The callout's state as the engine stamps it: data-qs-state is 'running'
# while an act runs, 'done' when check() returned a note, 'failed' when it
# returned null, 'idle' on a step with no act.
STATE_JS = """() => {
    const c = document.getElementById('qs-callout');
    const r = c && c.querySelector('.qs-result');
    return {
        state: c ? c.getAttribute('data-qs-state') : null,
        visible: !!c && c.style.display !== 'none',
        title: c && c.querySelector('h3') ? c.querySelector('h3').textContent : '',
        note: r ? r.textContent : '',
        fail: !!(r && r.classList.contains('qs-result-fail')),
        qs: window.QuickStart.state(),
    };
}"""

# A step's anchor, resolved the way quickstart.js resolves it (a target may
# be a function naming hardware the tour minted): found, and not 0x0.
CHECK_TARGET_JS = """([n, i]) => {
    const s = window.QuickStart.tours()[n][i];
    if (s.center || !s.target) return {found: null, visible: null, target: null};
    const t = typeof s.target === 'function' ? s.target() : s.target;
    const el = document.querySelector(t);
    if (!el) return {found: false, visible: false, target: t};
    const r = el.getBoundingClientRect();
    return {found: true, visible: !(r.width === 0 && r.height === 0), target: t};
}"""

# The user's world, canonical: the project (order-insensitive, underscore
# caches dropped), history, view, the cable-sheet flags and what is open.
WORLD_JS = """() => {
    const app = window.app;
    const keys = [];
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k.startsWith('lrd_data_cable_sheet_') || k.startsWith('lrd_cable_sheet_')) keys.push(k);
    }
    const pop = document.getElementById('hw-gear-popover');
    const menu = document.getElementById('context-menu');
    const exp = document.getElementById('export-modal');
    const tab = document.querySelector('.view-tab.active[data-mode]');
    return {
        project: app._canonicalJson(app.project),
        historyLength: app.history.length,
        historyIndex: app.historyIndex,
        mode: tab ? tab.dataset.mode : null,
        sheetKeys: keys.sort(),
        popover: !!pop && pop.style.display === 'block',
        menu: !!menu && menu.style.display === 'block',
        exportOpen: !!exp && exp.style.display === 'block',
        sweep: !!(app._traySweep || app._sweepSelection),
        editing: !!app._overrideEditing,
        layers: (app.project.layers || []).map(l => l.name),
    };
}"""

QUICKSTART_JS = os.path.join(os.path.dirname(__file__), '..', 'src', 'static',
                             'js', 'quickstart.js')

# Words the app no longer says, and where each was retired:
#   tails            - circuits, not tails (user ruling, 2026-08-30)
#   Signal + Power   - the export tick is Wiring; Power Wiring and Data
#                      Wiring are sheets of their own (2026-09-12)
#   N-way            - a snake is an "N channel snake" (2026-09-12)
#   Halves           - the port shape reads OPT Split / Split (2026-09-11)
#
# The tray's circuit chips carry the app's own `tail-<distro>-<n>-<t>` key
# (app-dock.js _dockBuildCircuitChip), and a demonstrating step drags one
# by that key; a hyphenated identifier is code, not copy, so the word
# followed by a hyphen is exempt. Prose - "tails", "the tail" - still fails.
RETIRED_WORDING = [
    (r'\btails?\b(?!-)', 'circuits, not tails'),
    (r'Signal \+ Power', 'the wiring sheets are Power Wiring and Data Wiring; '
                         'the tick is Wiring'),
    (r'-way\b', 'a snake is an N channel snake, never N-way'),
    (r'\bhalves\b', 'the port shape is OPT Split / Split, never Halves'),
]


def _retired_wording_hits(src):
    hits = []
    for pattern, rule in RETIRED_WORDING:
        for m in re.finditer(pattern, src, re.I):
            line = src.count('\n', 0, m.start()) + 1
            hits.append('line %d: %r (%s)' % (line, m.group(0), rule))
    return hits


def test_tour_copy_never_says_retired_words():
    """Every step body must say what the app says today. quickstart.js is
    tour copy plus machinery that never uses these words, so the whole
    file must stay clean of them - a step still saying "Signal + Power",
    "4-way", "Halves" or "tails" fails here with its line."""
    with open(QUICKSTART_JS, encoding='utf-8') as f:
        src = f.read()
    hits = _retired_wording_hits(src)
    assert not hits, 'quickstart.js still says:\n' + '\n'.join(hits)


def test_retired_wording_guard_catches_each_word():
    """The guard itself: each retired word, in a sentence shaped like a
    step body, is caught - so a silently broken pattern cannot pass."""
    for sample in ('one Signal + Power sheet', 'a 4-way snake',
                   'Halves the ports', 'circuits, not tails'):
        assert _retired_wording_hits(sample), sample
    assert not _retired_wording_hits(
        'SNAKE A · 4 channel; OPT Split; Power Wiring and Data Wiring')


def test_tour_registry_exposes_all_tours(page):
    names = page.evaluate("Object.keys(window.QuickStart.tours())")
    assert {'quick', 'whatsNew', 'advanced'} <= set(names), names
    for name in names:
        count = page.evaluate(
            "(n) => window.QuickStart.tours()[n].length", name)
        assert count > 0, f"tour {name} has no steps"


def _strip_html(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'&[a-z]+;|&#\d+;', 'x', s)
    return s


def test_step_copy_is_one_action(page):
    """Every step that is not an intro/outro has an act and a check, and
    its body is one or two sentences of at most 220 characters - the
    single action, in the user's terms."""
    shapes = page.evaluate("""() => {
        const out = {};
        const tours = window.QuickStart.tours();
        for (const n of Object.keys(tours)) {
            out[n] = tours[n].map(s => ({
                title: s.title, body: s.body, center: !!s.center,
                act: typeof s.act === 'function',
                check: typeof s.check === 'function',
            }));
        }
        return out;
    }""")
    problems = []
    for name, steps in shapes.items():
        for i, s in enumerate(steps):
            where = f"{name} step {i + 1} ({s['title']!r})"
            body = _strip_html(s['body'])
            if len(body) > 220:
                problems.append(f"{where}: body is {len(body)} chars")
            sentences = len(re.findall(r'[.!?](\s|$)', body))
            if sentences > 2:
                problems.append(f"{where}: body has {sentences} sentences")
            if s['center']:
                continue
            if not s['act']:
                problems.append(f"{where}: no act")
            if not s['check']:
                problems.append(f"{where}: no check")
    assert not problems, "\n".join(problems)


def _wait_step(page, index, timeout=45):
    """Until the engine is on `index` and its act has settled."""
    deadline = time.time() + timeout
    st = None
    while time.time() < deadline:
        st = page.evaluate(STATE_JS)
        if st['qs']['index'] == index and st['state'] in ('done', 'failed', 'idle'):
            return st
        time.sleep(0.1)
    return st


def _start(page, tour, speed=2):
    page.evaluate("(s) => window.QuickStart.setSpeed(s)", speed)
    page.evaluate("(n) => { window.QuickStart.startTour(n); }", tour)
    return _wait_step(page, 0)


def _end(page):
    page.evaluate("() => window.QuickStart.end()")
    page.wait_for_timeout(300)


def _step_index(page, tour, title_part):
    titles = page.evaluate(
        "(n) => window.QuickStart.tours()[n].map(s => s.title)", tour)
    hits = [i for i, t in enumerate(titles) if title_part in t]
    assert hits, f'{tour}: no step titled like {title_part!r} in {titles}'
    return hits[0]


def _drive_to(page, tour, index, speed=2):
    _start(page, tour, speed)
    for i in range(index):
        page.locator('#qs-next').click()
        _wait_step(page, i + 1)
    return page.evaluate(STATE_JS)


def test_every_step_acts_and_checks(page):
    """Each tour, driven to the end: every step's anchor resolves and is
    visible once its act settled, and its check returned a note. Every
    failing step is named in one message."""
    problems = []
    names = page.evaluate("Object.keys(window.QuickStart.tours())")
    for name in names:
        n = page.evaluate("(n) => window.QuickStart.tours()[n].length", name)
        st = _start(page, name, speed=2)
        for i in range(n):
            st = _wait_step(page, i)
            where = f"{name} step {i + 1} ({st['title']!r})"
            if not st or st['qs']['index'] != i:
                problems.append(f"{where}: the engine never settled on this step ({st})")
                break
            res = page.evaluate(CHECK_TARGET_JS, [name, i])
            if res['found'] is False:
                problems.append(f"{where}: selector {res['target']!r} matches nothing")
            elif res['found'] and not res['visible']:
                problems.append(f"{where}: {res['target']!r} is 0x0 in this step's view")
            if st['state'] == 'failed' or st['fail']:
                problems.append(f"{where}: check() returned null - {st['note']!r}")
            elif st['state'] == 'done' and not st['note'].strip():
                problems.append(f"{where}: no result note")
            if i < n - 1:
                page.locator('#qs-next').click()
        _end(page)
    assert not problems, "\n".join(problems)


def test_back_replays_the_previous_step(page):
    """Back restores the snapshot taken at the previous step's entry and
    replays its act: from the step after "Name it on its header", Back
    shows that step's note again, and the project holds exactly one
    processor named SR - no duplicate from the replay."""
    i = _step_index(page, 'advanced', 'Name it on its header')
    st = _drive_to(page, 'advanced', i + 1)
    assert st['qs']['index'] == i + 1, st
    page.locator('#qs-back').click()
    st = _wait_step(page, i)
    assert 'Name it' in st['title'], st
    assert st['state'] == 'done' and not st['fail'], st
    assert 'SR-1' in st['note'], st['note']
    procs = page.evaluate(
        "() => (window.app._processorsResolved || []).map(p => p.name)")
    assert procs == ['SR'], procs
    _end(page)


def test_exit_puts_the_users_project_back(page):
    """Skip mid-tour: the user's own project comes back deep-equal, with
    the same history, view and cable-sheet flags, and nothing the tour
    opened left standing."""
    page.evaluate(SEED_JS)
    page.wait_for_timeout(600)
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_timeout(300)
    before = page.evaluate(WORLD_JS)
    assert 'TOUR WALL' in before['layers'], before['layers']

    i = _step_index(page, 'advanced', 'loose port')
    _drive_to(page, 'advanced', i)
    mid = page.evaluate(WORLD_JS)
    assert 'DEMO WALL' in mid['layers'], mid['layers']
    page.locator('#qs-skip').click()
    page.wait_for_timeout(1500)

    after = page.evaluate(WORLD_JS)
    assert after['project'] == before['project'], 'the project did not come back deep-equal'
    assert after['historyLength'] == before['historyLength']
    assert after['historyIndex'] == before['historyIndex']
    assert after['mode'] == before['mode']
    assert after['sheetKeys'] == before['sheetKeys']
    assert not after['popover'] and not after['menu'] and not after['exportOpen']
    assert not after['sweep'] and not after['editing']
    assert not page.evaluate("window.QuickStart.state().visible")
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(200)


def test_escape_mid_act_does_not_corrupt(page):
    """Escape while an act runs is not the tour's to take (the app's own
    Escape cancels drags, sweeps and popovers): the tour either ignores it
    and finishes the step, or exits cleanly - and either way the user's
    project is back once the tour ends."""
    page.evaluate(SEED_JS)
    page.wait_for_timeout(600)
    before = page.evaluate(WORLD_JS)
    page.evaluate("() => window.QuickStart.setSpeed(1)")
    page.evaluate("() => { window.QuickStart.startTour('advanced'); }")
    _wait_step(page, 0)
    page.locator('#qs-next').click()
    deadline = time.time() + 10
    while time.time() < deadline:
        st = page.evaluate(STATE_JS)
        if st['qs']['index'] == 1 and st['state'] == 'running':
            break
        time.sleep(0.05)
    assert st['state'] == 'running', st
    page.keyboard.press('Escape')
    st = _wait_step(page, 1)
    if st['visible']:
        # ignored: the step finished as if nothing happened
        assert st['state'] == 'done' and not st['fail'], st
        _end(page)
    page.wait_for_timeout(1200)
    after = page.evaluate(WORLD_JS)
    assert after['project'] == before['project']
    assert not page.evaluate("window.QuickStart.state().visible")


PREFS_JS = """async (patch) => {
    const r = await fetch('/api/preferences');
    const prefs = await r.json();
    if (patch) {
        Object.assign(prefs, patch);
        await fetch('/api/preferences', {method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(prefs)});
        window.app._serverPreferences = prefs;
    }
    return prefs;
}"""


def test_tour_leaves_preferences_alone(page):
    """A step that writes a PREFERENCE (the binder's title block tick is
    one) must not leave it changed: a user whose title block was off ends
    the tour with it off, on the server and in the dialog."""
    original = page.evaluate(PREFS_JS, None)
    page.evaluate(PREFS_JS, {'binderTitleBlock': False})
    page.wait_for_timeout(300)
    try:
        i = _step_index(page, 'advanced', 'Border and title block')
        st = _drive_to(page, 'advanced', i)
        assert st['state'] == 'done' and not st['fail'], st
        page.locator('#qs-skip').click()
        page.wait_for_timeout(1500)
        prefs = page.evaluate(PREFS_JS, None)
        assert prefs.get('binderTitleBlock') is False, prefs.get('binderTitleBlock')
        assert page.evaluate("window.app.getPreferences().binderTitleBlock") is False
        page.evaluate("window.app.openExportModal('binder')")
        page.wait_for_timeout(300)
        assert not page.evaluate(
            "document.getElementById('export-binder-title-block').checked"
        ), 'the export dialog ticks the title block the tour turned on'
        page.evaluate("document.getElementById('export-modal').style.display = 'none'")
    finally:
        page.evaluate(PREFS_JS, {'binderTitleBlock': original.get('binderTitleBlock', True)})
        page.wait_for_timeout(200)


def test_reload_mid_tour_recovers_the_project(page):
    """While a tour runs the server holds the scratch show. A reload
    mid-tour (or a crash) must not cost the user their project: the world
    stashed at tour start is put back on boot and the stash is cleared."""
    page.evaluate(SEED_JS)
    page.wait_for_timeout(600)
    before = page.evaluate(WORLD_JS)
    assert 'TOUR WALL' in before['layers']
    i = _step_index(page, 'advanced', 'Name it on its header')
    _drive_to(page, 'advanced', i)
    assert page.evaluate("!!localStorage.getItem('lrd_tour_saved_world')")
    assert 'DEMO WALL' in page.evaluate(WORLD_JS)['layers']

    page.reload(wait_until='domcontentloaded')
    deadline = time.time() + 20
    while time.time() < deadline:
        ready = page.evaluate("""() => !!(window.app && window.app.project
            && !localStorage.getItem('lrd_tour_saved_world')
            && (window.app.project.layers || []).some(l => l.name === 'TOUR WALL'))""")
        if ready:
            break
        time.sleep(0.2)
    page.wait_for_timeout(800)
    after = page.evaluate(WORLD_JS)
    assert after['layers'] == before['layers'], after['layers']
    assert after['project'] == before['project'], 'the recovered project is not the seeded one'
    assert not page.evaluate("!!localStorage.getItem('lrd_tour_saved_world')")
    assert not page.evaluate("window.QuickStart.state().visible")
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(200)


def test_whats_new_launches_from_help_menu(page):
    """The Help menu entry and its handler both reach the What's New tour."""
    assert page.evaluate(
        "!!document.querySelector('#menu-help [data-action=\\'whats-new-tour\\']')"
    ), "Help menu has no What's New entry"
    page.evaluate("window.app.handleMenuAction('whats-new-tour')")
    st = _wait_step(page, 0)
    assert 'new in 0.12' in st['title'].lower(), st
    _end(page)
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(200)
