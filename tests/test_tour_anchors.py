"""Every guided-tour step's anchor must resolve in a seeded DOM.

The tours in quickstart.js anchor callouts to DOM selectors. A selector that
rots (the element renamed or removed) does not error - the machinery quietly
centers the callout - so nothing but this suite notices a tour pointing at
nothing. The test enumerates the steps programmatically from
window.QuickStart.tours(), so a tour or step added later is covered without
touching this file.

Seeding: dock-anchored steps (processor headers, gears, distro legs, multi
slots, circuit chips, the cable sheet's ext column) need hardware to exist,
so the module seeds one wall, one processor with a named card whose ports
are placed on the wall and four of them snaked (platform-matched, per the
platform wall), and one 3-phase distro with a multi landed on the wall.

Each tour is then driven for real - startTour(), then #qs-next through every
step - so each step's before() hook (view switches, opening the cable sheet
or the export dialog) runs exactly as it does for a user, and the anchor is
checked in the view the step shows it in. A step's after() hook puts back
what before() opened; test_skip_puts_back_what_a_step_opened proves it.

Run locally (each session takes its own free port, so it runs beside
any other):
    python -m pytest tests/test_tour_anchors.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


# One wall on a platform-matched processor with a named card, its ports
# placed on the wall and four of them on a snake, plus one 3-phase distro
# with a multi landed: enough hardware that every dock-anchored selector
# (proc name, grip, gear, slot, legs line, chip grid, the open cable sheet
# and its ext column) has something to resolve to.
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

CHECK_TARGET_JS = """(t) => {
    if (!t) return {found: null, visible: null};
    const el = document.querySelector(t);
    if (!el) return {found: false, visible: false};
    const r = el.getBoundingClientRect();
    // Mirror quickstart.js targetRect(): 0x0 counts as not there.
    return {found: true, visible: !(r.width === 0 && r.height === 0)};
}"""


QUICKSTART_JS = os.path.join(os.path.dirname(__file__), '..', 'src', 'static',
                             'js', 'quickstart.js')

# Words the app no longer says, and where each was retired:
#   tails            - circuits, not tails (user ruling, 2026-08-30)
#   Signal + Power   - the export tick is Wiring; Power Wiring and Data
#                      Wiring are sheets of their own (2026-09-12)
#   N-way            - a snake is an "N channel snake" (2026-09-12)
#   Halves           - the port shape reads OPT Split / Split (2026-09-11)
RETIRED_WORDING = [
    (r'\btails?\b', 'circuits, not tails'),
    (r'Signal \+ Power', 'the wiring sheets are Power Wiring and Data Wiring; '
                         'the tick is Wiring'),
    (r'-way\b', 'a snake is an N channel snake, never N-way'),
    (r'\bhalves\b', 'the port shape is OPT Split / Split, never Halves'),
]


def _retired_wording_hits(src):
    import re
    hits = []
    for pattern, rule in RETIRED_WORDING:
        for m in re.finditer(pattern, src, re.I):
            line = src.count('\n', 0, m.start()) + 1
            hits.append('line %d: %r (%s)' % (line, m.group(0), rule))
    return hits


def test_tour_copy_never_says_retired_words():
    """Every step body must say what the app says today. quickstart.js is
    tour copy plus a little machinery that never uses these words, so the
    whole file must stay clean of them - a step still saying "Signal +
    Power", "4-way", "Halves" or "tails" fails here with its line."""
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


def test_every_tour_step_anchor_resolves(page):
    page.evaluate(SEED_JS)
    page.wait_for_timeout(600)

    names = page.evaluate("Object.keys(window.QuickStart.tours())")
    problems = []
    for name in names:
        targets = page.evaluate(
            "(n) => window.QuickStart.tours()[n].map(s => s.target || null)",
            name)
        page.evaluate("(n) => window.QuickStart.startTour(n)", name)
        page.wait_for_timeout(600)  # first step's before() re-render
        for i, target in enumerate(targets):
            title = page.locator('#qs-callout h3').text_content() or ''
            assert title.strip(), f"{name} step {i + 1}: callout did not render"
            if target:
                res = page.evaluate(CHECK_TARGET_JS, target)
                if not res['found']:
                    problems.append(
                        f"{name} step {i + 1} ({title!r}): selector "
                        f"{target!r} matches nothing")
                elif not res['visible']:
                    problems.append(
                        f"{name} step {i + 1} ({title!r}): {target!r} "
                        f"resolves but is 0x0 in this step's view")
            if i < len(targets) - 1:
                page.locator('#qs-next').click()
                page.wait_for_timeout(450)  # covers before()'s 260ms re-render
        page.evaluate("window.QuickStart.end()")
        page.wait_for_timeout(200)
    assert not problems, "\n".join(problems)
    # leave the app back on the pixel map for anything after us
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(200)


def _step_index(page, tour, title_part):
    titles = page.evaluate(
        "(n) => window.QuickStart.tours()[n].map(s => s.title)", tour)
    hits = [i for i, t in enumerate(titles) if title_part in t]
    assert hits, f'{tour}: no step titled like {title_part!r} in {titles}'
    return hits[0]


def _drive_to(page, tour, index):
    page.evaluate("(n) => window.QuickStart.startTour(n)", tour)
    page.wait_for_timeout(600)
    for _ in range(index):
        page.locator('#qs-next').click()
        page.wait_for_timeout(450)
    title = page.locator('#qs-callout h3').text_content() or ''
    return title


SHEET_OPEN_JS = ("!!document.querySelector('#hardware-dock-body "
                 ".hw-dock-cablebtn-data.hw-dock-cablebtn-on')")
EXPORT_OPEN_JS = ("(() => { const m = document.getElementById('export-modal');"
                  " return !!m && m.style.display === 'block'; })()")


def test_skip_puts_back_what_a_step_opened(page):
    """A step that opens the cable sheet or the export dialog to point into
    it closes it again when the tour leaves the step - by Skip as much as
    by Next - so a tour never leaves a sheet or a dialog standing."""
    page.evaluate(SEED_JS)
    page.wait_for_timeout(600)

    # the ext column: the data cable sheet opens for the step, closes on Skip
    i = _step_index(page, 'whatsNew', 'ext column')
    title = _drive_to(page, 'whatsNew', i)
    assert 'ext' in title, title
    assert page.evaluate(SHEET_OPEN_JS), 'the ext step did not open the sheet'
    res = page.evaluate(CHECK_TARGET_JS, page.evaluate(
        "(i) => window.QuickStart.tours().whatsNew[i].target", i))
    assert res['found'] and res['visible'], res
    page.locator('#qs-skip').click()
    page.wait_for_timeout(200)
    assert not page.evaluate(SHEET_OPEN_JS), 'Skip left the cable sheet open'

    # the binder steps: the export dialog opens on Binder, closes on Skip
    i = _step_index(page, 'advanced', 'Screen order')
    title = _drive_to(page, 'advanced', i)
    assert 'Screen order' in title, title
    assert page.evaluate(EXPORT_OPEN_JS), 'the Screen order step did not open the export dialog'
    assert page.evaluate("document.getElementById('export-format').value") == 'binder'
    page.locator('#qs-skip').click()
    page.wait_for_timeout(200)
    assert not page.evaluate(EXPORT_OPEN_JS), 'Skip left the export dialog open'

    # and Next past the last binder step closes it too
    i = _step_index(page, 'advanced', 'Border and title block')
    _drive_to(page, 'advanced', i)
    assert page.evaluate(EXPORT_OPEN_JS)
    page.locator('#qs-next').click()
    page.wait_for_timeout(450)
    assert not page.evaluate(EXPORT_OPEN_JS), 'Next left the export dialog open'
    page.evaluate("window.QuickStart.end()")
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(200)


def test_whats_new_launches_from_help_menu(page):
    """The Help menu entry and its handler both reach the What's New tour."""
    assert page.evaluate(
        "!!document.querySelector('#menu-help [data-action=\\'whats-new-tour\\']')"
    ), "Help menu has no What's New entry"
    page.evaluate("window.app.handleMenuAction('whats-new-tour')")
    page.wait_for_timeout(600)
    title = page.locator('#qs-callout h3').text_content() or ''
    assert 'new in 0.12' in title.lower(), title
    page.evaluate("window.QuickStart.end()")
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(200)
