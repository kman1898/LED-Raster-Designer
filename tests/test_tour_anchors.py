"""Every guided-tour step's anchor must resolve in a seeded DOM.

The tours in quickstart.js anchor callouts to DOM selectors. A selector that
rots (the element renamed or removed) does not error - the machinery quietly
centers the callout - so nothing but this suite notices a tour pointing at
nothing. The test enumerates the steps programmatically from
window.QuickStart.tours(), so a tour or step added later is covered without
touching this file.

Seeding: dock-anchored steps (processor headers, gears, distro legs, multi
slots, circuit chips) need hardware to exist, so the module seeds one wall,
one processor (platform-matched, per the platform wall) and one 3-phase
distro - the same shape test_hardware_dock.py uses.

Each tour is then driven for real - startTour(), then #qs-next through every
step - so each step's before() hook (view switches) runs exactly as it does
for a user, and the anchor is checked in the view the step shows it in.

Run locally (ONE pytest at a time - the browser-test server uses a fixed
port):
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


# One wall on a platform-matched processor plus one 3-phase distro: enough
# hardware that every dock-anchored selector (proc name, gear, slot, legs
# line, chip grid) has something to resolve to.
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'TOUR WALL', columns: 10, rows: 5,
                              cabinet_width: 200, cabinet_height: 200})});
    await fetch('/api/processors', {method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({deviceId: 'novastar-mx40-pro'})});
    const app = window.app;
    const p1 = await (await fetch('/api/project')).json();
    for (const l of p1.layers) {
        // The MX40 Pro is COEX gear; since the platform wall a screen only
        // lands on gear its Processing setting matches.
        await fetch(`/api/layer/${l.id}`, {method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({powerVoltage: 208, powerAmperage: 20,
                                  processorType: 'novastar-coex-1g'})});
    }
    const p = await (await fetch('/api/project')).json();
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.addDistro({name: 'PD'});
    await app.refreshProcessors();
    app.renderLayers();
    app.resetHistory('Tour Anchor Seed');
    return p.layers[0].id;
}"""

CHECK_TARGET_JS = """(t) => {
    if (!t) return {found: null, visible: null};
    const el = document.querySelector(t);
    if (!el) return {found: false, visible: false};
    const r = el.getBoundingClientRect();
    // Mirror quickstart.js targetRect(): 0x0 counts as not there.
    return {found: true, visible: !(r.width === 0 && r.height === 0)};
}"""


def test_tour_copy_says_circuits_not_tails():
    """'tails' is banned display language (user ruling, 2026-08-30 -
    circuits, not tails). quickstart.js is tour copy plus a little
    machinery that never says the word, so the whole file must stay
    clean of it."""
    import re
    path = os.path.join(os.path.dirname(__file__), '..', 'src', 'static',
                        'js', 'quickstart.js')
    with open(path, encoding='utf-8') as f:
        src = f.read()
    hits = re.findall(r'\btails?\b', src, re.I)
    assert not hits, (
        'quickstart.js says %r; UI copy says circuits, not tails' % hits)


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
