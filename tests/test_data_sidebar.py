"""The middle panels are gone: the dock and the left sidebar split the estate.

The Signal and Power middle sidebars were a stop on the way to the hardware
dock. The per-thing editors they held - processor cards, port label rows, the
soca tiles, splitter rows, distro cards - live on the dock's own sections and
chips now, where the thing being edited is the thing on screen; the per-screen
knobs (fallback label templates, breakout type, splitter packing, brackets)
moved into the left sidebar's Data Settings / Power Settings panels; and the
issue boxes became the slim strip under the dock's header. The canvas gets the
whole middle back in every view.

What these tests pin, now that the consolidation has happened:

* The retired sidebars left NO markup behind - no #data-sidebar, no
  #power-sidebar, no toggles - in any view, and the canvas starts at the left
  sidebar's right edge everywhere. The dock is in layout only in the two
  hardware views (its deep geometry lives in tests/test_sidebar_resize.py and
  tests/test_hardware_dock.py; here only the light check).
* The editors that survived moved WHOLE: each id exists exactly once, in the
  left sidebar. The ids of the per-port / per-circuit list editors, the three
  Power hosts and the processor list are in no document at all - a leftover
  copy would answer the same getElementById and data-lrd-field lookups as the
  new home and fight it for state and focus.
* The dock's header chrome (add pickers, the attachment flag, the fold
  chevron, the issues strip) lives exactly once, inside #hardware-dock.
* Editing a field on a dock header and pressing Tab still leaves focus in a
  real keyed control after the rebuild that follows - the same
  _preserveEditorFocus contract the middle panels' editors carried, now
  proved against the dock's inline name fields.
* The one section-collapse machinery works on the left sidebar's named
  headers AND on the dock's generated sections (cards, distros, multis),
  with per-id persistence that is independent of the dock's own collapse.
  The deep dock-section coverage lives in tests/test_hardware_dock.py; the
  checks here pin that the SAME machinery reached the new homes.

Run locally:
    python3 -m pytest tests/test_data_sidebar.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it
    (see conftest.server_project_guard)."""


ALL_VIEWS = ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power']
DOCK_VIEWS = ['data-flow', 'power']

# Every element of the two retired sidebars' shells. None of these may exist
# in ANY view: the consolidation removed the panels outright, it did not hide
# them, and a hidden husk would still answer id lookups.
RETIRED_SHELL_IDS = ['data-sidebar', 'data-sidebar-toggle',
                     'power-sidebar', 'power-sidebar-toggle']


# Build our OWN project through the real endpoints. The live server is shared
# with every other browser test file, and inheriting whatever the previous one
# left behind has produced "passes alone, fails together" twice in this repo.
#
# 4x4 of 128px cabinets is deliberate: it builds at least two ports and, at
# the power seed's 208V/20A/400W, more than one circuit - so the dock has
# real chips and multi sections to test against.
RESET_JS = """async () => {
    const app = window.app;
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    await fetch('/api/layer/add', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: 'SignalPanel',
            columns: 4, rows: 4, cabinet_width: 128, cabinet_height: 128,
        }),
    });
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('data_sidebar_test_reset');
    const screen = app.project.layers.find(l => (l.type || 'screen') === 'screen');
    app.currentLayer = screen;
    app.selectedLayerIds = new Set([screen.id]);
    app.lastSelectedLayerId = screen.id;
    app.renderLayers();
    app.loadLayerToInputs(screen);
    app.updatePortCapacityDisplay();
    // The per-port list editor died with the Signal sidebar; the entry point
    // survives as a deliberate no-op so every "labels moved" path keeps
    // working. Calling it here pins exactly that: safe to call, does nothing.
    app.updatePortLabelEditor();
    if (window.canvasRenderer) window.canvasRenderer.render();
    return screen.id;
}"""


# The dock's power side only has sections once the screen has circuits AND a
# multi has a distro under it: an unassigned multi has no dock section, so
# no inline name/length editor exists until the assignment is made. Settings
# go through the real static fields (their change handlers and the deferred
# rebuild they schedule are things under test), the assignment through the
# same app calls the drag-drop path uses.
POWER_SEED_JS = """() => {
    const app = window.app;
    const set = (id, v) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.value = v;
        el.dispatchEvent(new Event('change', { bubbles: true }));
    };
    set('power-voltage-select', '208');
    set('power-amperage-select', '20');
    set('power-panel-watts', '400');
    if (!app.getDistros().length) app.addDistro();
    const d = app.getDistros()[0];
    const layer = app.currentLayer;
    if (((layer.powerSocaDistro || {})[1]) !== d.id) {
        app.setSocaDistro(layer, 1, d.id);
    }
    app.refreshSocaRuns();
    app.renderHardwareDock();
    return { distros: app.getDistros().length,
             distroId: d.id, layerId: layer.id,
             phase: Number(d.phase),
             circuits: app.screenCircuitCount(app.currentLayer) };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    assert pg.evaluate(RESET_JS), "test project was not created"
    pg.wait_for_timeout(600)
    yield pg
    context.close()


# ── helpers ───────────────────────────────────────────────────────────────

STATE_JS = """() => {
    const read = (id) => {
        const el = document.getElementById(id);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
            displayed: getComputedStyle(el).display !== 'none',
            collapsed: el.classList.contains('collapsed'),
            width: Math.round(r.width),
            height: Math.round(r.height),
            left: Math.round(r.left),
            right: Math.round(r.right),
        };
    };
    return {
        left: read('left-sidebar'),
        right: read('right-sidebar'),
        canvas: read('canvas-container'),
        dock: read('hardware-dock'),
    };
}"""


def open_view(page, mode):
    page.locator(f'[data-mode="{mode}"]').click()
    page.wait_for_timeout(400)


def state(page):
    return page.evaluate(STATE_JS)


def seed_power(page):
    open_view(page, 'power')
    seeded = page.evaluate(POWER_SEED_JS)
    page.wait_for_timeout(600)
    assert seeded['circuits'] > 0, f"the test screen drew no circuits: {seeded}"
    assert seeded['distros'] > 0, f"no distro exists: {seeded}"
    return seeded


# ── the retired sidebars are gone, and the canvas got the room back ───────

@pytest.mark.parametrize('mode', ALL_VIEWS)
def test_the_retired_sidebars_left_no_markup_behind(page, mode):
    """Absent from the DOM entirely - not hidden, not collapsed. A husk left
    in the markup would still win getElementById races and still carry the
    old localStorage-driven collapse state nobody can see."""
    open_view(page, mode)
    found = page.evaluate(
        """(ids) => ids.filter(
               id => document.querySelectorAll('#' + id).length)""",
        RETIRED_SHELL_IDS)
    assert found == [], (
        f"retired sidebar markup still in the DOM in {mode}: {found}")


@pytest.mark.parametrize('mode', ALL_VIEWS)
def test_the_canvas_starts_at_the_left_sidebars_edge(page, mode):
    """The width the middle panels took is returned in EVERY view - the dock
    steals height in its two views, never width."""
    open_view(page, mode)
    s = state(page)
    assert abs(s['canvas']['left'] - s['left']['right']) <= 1, (
        f"the canvas does not start at the left sidebar's edge in {mode}: "
        f"canvas left {s['canvas']['left']}, sidebar right {s['left']['right']}")


def test_the_dock_is_in_layout_only_in_the_hardware_views(page):
    """The light check only - the deep dock geometry (height stolen and
    returned, fold behaviour) lives in tests/test_sidebar_resize.py and
    tests/test_hardware_dock.py. Plus the outcome the old distro-list test
    pinned: project-level power hardware paints in Power view and nowhere
    else, even though the project still has its distro."""
    seed_power(page)
    assert page.evaluate(
        """() => document.querySelectorAll(
               '[data-lrd-sec^="hwdock-distro-"]').length""") > 0, (
        "the seeded distro built no dock section, so this would prove nothing")
    for mode in ALL_VIEWS:
        open_view(page, mode)
        s = state(page)
        if mode in DOCK_VIEWS:
            assert s['dock']['displayed'], f"no dock in {mode}: {s['dock']}"
            assert s['dock']['height'] > 0, (
                f"the dock is in layout but flat in {mode}: {s['dock']}")
        else:
            assert not s['dock']['displayed'], (
                f"the dock is still in layout in {mode}: {s['dock']}")
            painted = page.evaluate(
                """() => [...document.querySelectorAll(
                       '[data-lrd-sec^="hwdock-distro-"]')]
                       .filter(el => el.getClientRects().length > 0).length""")
            assert painted == 0, (
                f"distro hardware is drawn in {mode}: {painted} sections")


# ── every editor id has exactly one home ──────────────────────────────────

# The per-screen knobs that survived the consolidation, all re-homed into the
# left sidebar's Data Settings / Power Settings panels. They were MOVED, not
# copied: a second element with one of these ids would split
# document.getElementById from the focus-restore lookup and break editing
# without failing anything.
LEFT_SIDEBAR_IDS = [
    # Data Settings - Fallback Labels
    'port-label-template-primary', 'port-label-template-return',
    'port-label-bulk-primary', 'port-label-bulk-return',
    'port-label-apply-selected', 'port-label-clear-selected',
    # Power Settings - Circuit Labels
    'power-label-template', 'power-label-bulk',
    'power-label-apply-selected', 'power-label-clear-selected',
    # Power Settings - Multis & Splitters
    'power-breakout-type', 'power-splitters-enabled',
    'power-splitters-maxways', 'show-soca-brackets',
]

# The list editors and hosts that died with the sidebars. The checkbox
# select/deselect pairs go with the lists they selected in: Apply/Clear now
# target ALL ports / circuits of the current screen (the consolidation's
# re-pinned contract - there are no per-row checkboxes anywhere to subset).
RETIRED_IDS = [
    'port-label-list', 'port-label-select-all', 'port-label-deselect-all',
    'power-label-list', 'power-label-select-all', 'power-label-deselect-all',
    'port-assignment-issues', 'port-assignment-foot',
    'processor-list', 'processor-add-row',
    'power-soca-runs', 'power-splitters', 'power-distros',
    # Auto-numbering is retired outright (user ruling, 2026-09-03): nothing
    # lands on a card unless a person put it there, so a resurrected
    # checkbox would re-offer a switch that no longer exists.
    'port-assignment-auto', 'hw-dock-auto-wrap',
]

# The dock header bar's chrome - the retired panels' add rows and the
# attachment flag, re-homed onto the one hardware surface.
DOCK_HEAD_IDS = [
    'processor-add-device', 'processor-add-btn', 'power-distro-add',
    'hw-dock-flag', 'hw-dock-attach', 'hw-dock-fold', 'hw-dock-issues',
]


@pytest.mark.parametrize('element_id', LEFT_SIDEBAR_IDS)
def test_the_surviving_knobs_live_once_in_the_left_sidebar(page, element_id):
    found = page.evaluate(
        """(id) => ({
            total: document.querySelectorAll('[id="' + id + '"]').length,
            inLeft: document.querySelectorAll(
                '#left-sidebar [id="' + id + '"]').length,
        })""", element_id)
    assert found['total'] == 1, (
        f"#{element_id} is not unique in the document: {found}")
    assert found['inLeft'] == 1, (
        f"#{element_id} is not in the left sidebar: {found}")


@pytest.mark.parametrize('element_id', RETIRED_IDS)
def test_the_retired_editor_markup_is_gone(page, element_id):
    count = page.evaluate(
        "(id) => document.querySelectorAll('[id=\"' + id + '\"]').length",
        element_id)
    assert count == 0, (
        f"#{element_id} still exists ({count}) - the consolidation retired "
        f"it, and a leftover would answer the old lookups")


@pytest.mark.parametrize('element_id', DOCK_HEAD_IDS)
def test_the_dock_chrome_lives_once_inside_the_dock(page, element_id):
    found = page.evaluate(
        """(id) => ({
            total: document.querySelectorAll('[id="' + id + '"]').length,
            inDock: document.querySelectorAll(
                '#hardware-dock [id="' + id + '"]').length,
        })""", element_id)
    assert found['total'] == 1, (
        f"#{element_id} is not unique in the document: {found}")
    assert found['inDock'] == 1, (
        f"#{element_id} is not inside #hardware-dock: {found}")


# ── focus survives the dock rebuilds ──────────────────────────────────────

FOCUS_JS = """() => {
    const a = document.activeElement;
    return {
        tag: a ? a.tagName : null,
        id: a ? (a.id || null) : null,
        key: (a && a.dataset) ? (a.dataset.lrdField || null) : null,
        isBody: a === document.body,
        inDock: !!(a && a.closest && a.closest('#hardware-dock')),
        inLeft: !!(a && a.closest && a.closest('#left-sidebar')),
        stamped: !!(a && a.__stamp),
    };
}"""

# Stamp the dock's live controls. Element identity does not survive a
# rebuild, so a still-stamped control afterwards would mean no rebuild
# happened and the focus assertion would be passing for the wrong reason.
STAMP_DOCK_JS = """() => {
    const els = document.querySelectorAll(
        '#hardware-dock input, #hardware-dock button');
    els.forEach(el => { el.__stamp = 1; });
    return els.length;
}"""


def test_renaming_a_distro_and_tabbing_keeps_focus_in_a_real_control(page):
    """The distro's name edits inline on its dock header now. Its change
    handler writes the model synchronously and defers the dock rebuild one
    macrotask (_restateNaming -> _rebuildAfterGesture), so Tab lands on the
    header's Balance button first and _preserveEditorFocus restores it by
    data-lrd-field key after the wipe - the exact contract the retired
    distro rows carried, proved against their new home."""
    seeded = seed_power(page)
    assert seeded['phase'] == 3, (
        f"the seeded distro is not 3-phase, so its header carries no Balance "
        f"button for Tab to land on: {seeded}")
    name_key = f"distro-name-{seeded['distroId']}"
    # Tab's next stop after the name: the header's own Balance button.
    next_key = f"distro-balance-{seeded['distroId']}"

    stamped = page.evaluate(STAMP_DOCK_JS)
    assert stamped >= 2, f"the dock built no controls to test: {stamped}"

    page.evaluate(
        """(key) => document.querySelector(
               '[data-lrd-field="' + key + '"]').focus()""", name_key)
    page.keyboard.press("Control+A" if sys.platform != "darwin" else "Meta+A")
    page.keyboard.type("BEACH 1")
    page.keyboard.press("Tab")

    page.wait_for_function(
        """(key) => {
            const el = document.querySelector('[data-lrd-field="' + key + '"]');
            return !!el && !el.__stamp;
        }""", arg=next_key, timeout=5000)

    after = page.evaluate(FOCUS_JS)
    assert not after['isBody'], (
        f"focus fell to <body> after the dock rebuild: {after}")
    assert after['key'] == next_key, (
        f"focus is not back on the header's Balance button: {after}")
    assert after['inDock'], (
        f"focus is outside the dock, so the control it landed on is not the "
        f"re-homed editor's: {after}")
    assert not after['stamped'], (
        "the dock never rebuilt, so this proved nothing")

    assert page.evaluate(
        "() => window.app.getDistros()[0].name") == 'BEACH 1', (
        "the distro rename did not survive the move to the dock")


def test_renaming_a_multi_and_tabbing_keeps_focus_in_a_real_control(page):
    """The soca tiles' name and home-run length fields ride the occupied
    multi's dock header now, layer-qualified (the dock shows every screen
    where the old sidebar showed the current one). Same deferred-rebuild,
    restore-by-key doctrine as the distro rename above."""
    seeded = seed_power(page)
    name_key = f"power-soca-name-{seeded['layerId']}-1"
    len_key = f"power-soca-length-{seeded['layerId']}-1"

    built = page.evaluate(
        """() => [...document.querySelectorAll(
               '#hardware-dock [data-lrd-field]')].map(
                   el => el.dataset.lrdField)""")
    assert name_key in built, (
        f"no inline multi name field on the dock - was the multi assigned to "
        f"a distro? an unassigned multi has no dock section: {built}")
    assert len_key in built, f"no multi length field on the dock: {built}"
    # The circuit label editor came to the dock too - each occupied circuit
    # chip folds the override field the retired Circuit Labels list held.
    assert any(f.startswith('power-label-') for f in built), (
        f"no circuit label field on any dock chip: {built}")

    stamped = page.evaluate(STAMP_DOCK_JS)
    assert stamped >= 2, f"the dock built no controls to test: {stamped}"

    page.evaluate(
        """(key) => document.querySelector(
               '[data-lrd-field="' + key + '"]').focus()""", name_key)
    page.keyboard.press("Control+A" if sys.platform != "darwin" else "Meta+A")
    page.keyboard.type("FOH A")
    page.keyboard.press("Tab")

    page.wait_for_function(
        """(key) => {
            const el = document.querySelector('[data-lrd-field="' + key + '"]');
            return !!el && !el.__stamp;
        }""", arg=len_key, timeout=5000)

    after = page.evaluate(FOCUS_JS)
    assert not after['isBody'], (
        f"focus fell to <body> after the dock rebuild: {after}")
    assert after['key'] == len_key, (
        f"Tab did not move from the multi's name to its length field: {after}")
    assert after['inDock'], f"focus left the dock entirely: {after}"
    assert not after['stamped'], (
        "the dock never rebuilt, so this proved nothing")

    assert page.evaluate(
        """(lid) => {
            const l = window.app.project.layers.find(x => x.id === lid);
            return (l.powerSocaNames || {})['1'] || null;
        }""", seeded['layerId']) == 'FOH A', (
        "the multi rename did not survive the move to the dock")


def test_tabbing_out_of_the_last_static_power_field_lands_somewhere_real(page):
    """Watts per Panel used to be followed by the Power sidebar; its change
    handler still schedules rebuilds of the surfaces that read it (now the
    static knobs' sync and the dock), and an inline one would have destroyed
    the stop Tab was moving into."""
    seed_power(page)

    page.evaluate(
        "() => document.getElementById('power-panel-watts').focus()")
    page.keyboard.press("Control+A" if sys.platform != "darwin" else "Meta+A")
    page.keyboard.type("450")
    page.keyboard.press("Tab")
    page.wait_for_timeout(600)  # past the deferred rebuild

    after = page.evaluate(FOCUS_JS)
    assert not after['isBody'], (
        f"focus fell to <body> after leaving Watts per Panel: {after}")
    landed = page.evaluate(
        """() => {
            const a = document.activeElement;
            if (!a) return null;
            const home = a.closest('#left-sidebar') ? 'left'
                : a.closest('#hardware-dock') ? 'dock' : 'elsewhere';
            return { home, tag: a.tagName, cls: a.className,
                     visible: a.getClientRects().length > 0 };
        }""")
    assert landed['visible'], f"Tab landed on something not drawn: {landed}"
    assert landed['home'] in ('left', 'dock'), (
        f"Tab left the Power UI entirely: {landed}")
    assert page.evaluate(
        "() => parseFloat(window.app.currentLayer.panelWatts)") == 450, (
        "the edit did not commit when focus left the field")


# ── collapsible sections: the ▾ works everywhere it appears ───────────────
#
# Every titled section bar carried a decorative ▾ (theme.css ::after) that
# did nothing. It is a real arrow button with ONE behaviour everywhere
# (user spec, exact): a single click on the ARROW toggles the section, a
# DOUBLE-click anywhere on the header does the same, and a single click on
# the header does NOTHING - stray clicks are harmless. State persists per
# section (ledRasterPanelCollapsed_<id>), survives a reload, and is
# independent of the sidebar-level collapse. The body hides but never
# leaves the DOM, and a focus restore into a folded section auto-expands
# it. The dock's generated sections (cards, boxes, distros, multis) are
# wired by the same mechanism at every renderHardwareDock.

# (view, panel title) for the left-sidebar headers that survived the
# consolidation; the same wiring reaches every other .panel-header for free.
# The retired panels' headers (Processors, Port Numbering, Port Labels,
# Power Distribution) are covered by the retired-id tests above - they no
# longer exist to fold.
NAMED_HEADERS = [
    ('data-flow', 'Data Settings'),
    ('power', 'Power Settings'),
]


def header_of(page, title):
    return page.locator(f'.panel-header:has(h2:text-is("{title}"))')


HEADER_STATE_JS = """(title) => {
    const hdr = [...document.querySelectorAll('.panel-header')].find(h => {
        const t = h.querySelector('h2');
        return t && t.textContent.trim() === title;
    });
    if (!hdr) return null;
    const panel = hdr.parentElement;
    const content = panel.querySelector(':scope > .panel-content');
    const arrow = hdr.querySelector('.lrd-sec-arrow');
    return {
        id: panel.dataset.lrdSecId || null,
        hasArrow: !!arrow,
        arrowFontPx: arrow ? parseFloat(getComputedStyle(arrow).fontSize) : 0,
        arrowPainted: arrow ? arrow.getClientRects().length > 0 : false,
        collapsed: content ? getComputedStyle(content).display === 'none' : null,
        bodyInDom: !!content && content.isConnected,
        stored: panel.dataset.lrdSecId ? localStorage.getItem(
            'ledRasterPanelCollapsed_' + panel.dataset.lrdSecId) : null,
    };
}"""


def header_state(page, title):
    return page.evaluate(HEADER_STATE_JS, title)


@pytest.mark.parametrize('mode,title', NAMED_HEADERS)
def test_every_named_header_carries_a_live_visible_arrow(page, mode, title):
    open_view(page, mode)
    s = header_state(page, title)
    assert s, f"no panel header titled {title!r}"
    assert s['hasArrow'], f"{title} has no collapse arrow: {s}"
    assert s['arrowPainted'], f"{title}'s arrow is not painted: {s}"
    assert s['arrowFontPx'] >= 12, (
        f"{title}'s arrow is no bigger than the old 10px decorative glyph "
        f"it replaces: {s}")
    assert s['id'], f"{title} has no persistence id: {s}"


@pytest.mark.parametrize('mode,title', NAMED_HEADERS)
def test_arrow_click_collapses_and_header_single_click_is_inert(page, mode, title):
    open_view(page, mode)
    hdr = header_of(page, title)
    assert header_state(page, title)['collapsed'] is False
    # a single click on the header body does nothing - stray clicks harmless
    hdr.click()
    page.wait_for_timeout(100)
    assert header_state(page, title)['collapsed'] is False, (
        f"a single click on the {title} header must not collapse it")
    # a single click on the ARROW collapses; the body hides but stays in DOM
    hdr.locator('.lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    s = header_state(page, title)
    assert s['collapsed'] is True, f"the arrow did not collapse {title}: {s}"
    assert s['bodyInDom'], (
        f"{title}'s body left the DOM - collapse must hide, never detach")
    assert s['stored'] == '1', f"collapse did not persist for {title}: {s}"
    # and expands again
    hdr.locator('.lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert header_state(page, title)['collapsed'] is False


@pytest.mark.parametrize('mode,title', NAMED_HEADERS)
def test_double_click_anywhere_on_the_header_toggles(page, mode, title):
    open_view(page, mode)
    hdr = header_of(page, title)
    assert header_state(page, title)['collapsed'] is False
    hdr.dblclick()
    page.wait_for_timeout(100)
    assert header_state(page, title)['collapsed'] is True, (
        f"double-click on the {title} header must collapse it")
    hdr.dblclick()
    page.wait_for_timeout(100)
    assert header_state(page, title)['collapsed'] is False, (
        f"a second double-click must expand {title} again")


def test_the_section_collapsed_state_survives_a_reload(page):
    open_view(page, 'data-flow')
    hdr = header_of(page, 'Data Settings')
    hdr.locator('.lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert header_state(page, 'Data Settings')['collapsed'] is True
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, 'data-flow')
    s = header_state(page, 'Data Settings')
    assert s['collapsed'] is True, (
        f"Data Settings came back expanded after a reload: {s}")
    header_of(page, 'Data Settings').locator('.lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert header_state(page, 'Data Settings')['collapsed'] is False


# The dock sections' state, addressed by their declared data-lrd-sec id -
# the generated cousins of the static headers above.
DOCK_SEC_JS = """(secId) => {
    const head = document.querySelector('[data-lrd-sec="' + secId + '"]');
    if (!head) return null;
    const box = head.parentElement;
    const body = box.querySelector(':scope > .lrd-sec-body');
    const arrow = head.querySelector('.lrd-sec-arrow');
    return {
        wired: !!head.dataset.lrdSecWired,
        arrowPainted: !!arrow && arrow.getClientRects().length > 0,
        key: box.dataset.lrdSecId || null,
        collapsed: body ? getComputedStyle(body).display === 'none' : null,
        bodyInDom: !!body && body.isConnected,
        stored: localStorage.getItem('ledRasterPanelCollapsed_' + secId),
    };
}"""


def test_a_distro_dock_section_folds_and_survives_its_rebuilds(page):
    """The light check that the dock's distro section folds by the same
    machinery and re-applies its state across the innerHTML wipe every
    renderHardwareDock performs - the deep dock-section coverage lives in
    tests/test_hardware_dock.py."""
    seeded = seed_power(page)
    sec = f"hwdock-distro-{seeded['distroId']}"
    s = page.evaluate(DOCK_SEC_JS, sec)
    assert s and s['wired'], f"{sec} is not wired by the section machinery: {s}"
    assert s['arrowPainted'], f"{sec} carries no live arrow: {s}"
    assert s['key'] == sec, (
        f"{sec} persists outside the ledRasterPanelCollapsed_ convention: {s}")
    assert s['collapsed'] is False, f"{sec} started collapsed: {s}"

    page.locator(f'[data-lrd-sec="{sec}"] .lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    s = page.evaluate(DOCK_SEC_JS, sec)
    assert s['collapsed'] is True, f"the arrow did not fold {sec}: {s}"
    assert s['bodyInDom'], (
        f"{sec}'s body left the DOM - collapse must hide, never detach")
    assert s['stored'] == '1', f"the fold did not persist for {sec}: {s}"

    # The wipe-and-rewire: a folded section stays folded across a rebuild.
    page.evaluate("() => window.app.renderHardwareDock()")
    page.wait_for_timeout(100)
    s = page.evaluate(DOCK_SEC_JS, sec)
    assert s['collapsed'] is True, f"a rebuild re-expanded {sec}: {s}"

    page.locator(f'[data-lrd-sec="{sec}"] .lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert page.evaluate(DOCK_SEC_JS, sec)['collapsed'] is False


def test_focus_restore_into_a_folded_multi_section_expands_it(page):
    """The stated rule, against the dock: a field the app programmatically
    focuses (the _preserveEditorFocus restore after a rebuild) must be
    visible, so the folded multi section its circuit chip lives in opens
    rather than swallowing the focus - and the opening persists, or the next
    rebuild folds the field away again."""
    seeded = seed_power(page)
    sec = f"hwdock-multi-{seeded['distroId']}-1"
    out = page.evaluate("""async (sec) => {
        const app = window.app;
        const head = document.querySelector('[data-lrd-sec="' + sec + '"]');
        if (!head) return { missing: sec };
        const box = head.parentElement;
        // The circuit label fields live inside chips now, so the field a
        // user would be standing in is one whose chip is open - open it the
        // way they would, through the face.
        const tile = box.querySelector('.lrd-tile[data-lrd-tile]');
        if (tile && !tile.classList.contains('lrd-tile-open')) {
            tile.querySelector(':scope > .lrd-tile-face').click();
        }
        const el = box.querySelector('.lrd-tile-body input[data-lrd-field]');
        if (!el) return { skipped: true };
        el.focus();
        app._preserveEditorFocus();          // captures key + schedules restore
        app._setSectionCollapsed(box, true); // fold before the restore lands
        if (document.activeElement) document.activeElement.blur();
        await new Promise(r => setTimeout(r, 20));
        const body = box.querySelector(':scope > .lrd-sec-body');
        return {
            reopened: getComputedStyle(body).display !== 'none',
            focusedBack: document.activeElement === el,
            stored: localStorage.getItem('ledRasterPanelCollapsed_' + sec),
        };
    }""", sec)
    assert not out.get('missing'), (
        f"no dock section for the assigned multi: {out}")
    assert not out.get('skipped'), (
        "the multi's chips built no field to focus")
    assert out['reopened'], (
        f"the restore left the section folded around the focused field: {out}")
    assert out['focusedBack'], f"focus was not restored into the field: {out}"
    assert out['stored'] == '0', (
        f"the auto-expansion must persist, or the next rebuild folds the "
        f"field away again: {out}")


def test_section_collapse_is_independent_of_the_dock_collapse(page):
    """Folding the dock (the sidebar-level collapse, hardware-dock-toggle)
    and reopening it must not touch a folded section inside it - the two
    states live under different keys."""
    seeded = seed_power(page)
    sec = f"hwdock-distro-{seeded['distroId']}"
    page.locator(f'[data-lrd-sec="{sec}"] .lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert page.evaluate(DOCK_SEC_JS, sec)['collapsed'] is True

    page.locator('#hardware-dock-toggle').click()
    page.wait_for_timeout(400)
    assert page.evaluate(
        "() => document.getElementById('hardware-dock')"
        ".classList.contains('collapsed')"), "the dock did not collapse"
    page.locator('#hardware-dock-toggle').click()
    page.wait_for_timeout(400)

    s = page.evaluate(DOCK_SEC_JS, sec)
    assert s['collapsed'] is True, (
        f"collapsing the dock re-expanded the section inside it: {s}")
    keys = page.evaluate("""(sec) => ({
        section: localStorage.getItem('ledRasterPanelCollapsed_' + sec),
        dock: localStorage.getItem('ledRasterSidebarCollapsed_dock'),
    })""", sec)
    assert keys['section'] == '1' and keys['dock'] == '0', keys

    page.locator(f'[data-lrd-sec="{sec}"] .lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert page.evaluate(DOCK_SEC_JS, sec)['collapsed'] is False


def test_the_processor_cards_fold_by_the_same_machinery(page):
    """The processor hardware folds on the dock now: each card unit's header
    is a generated section head (data-lrd-sec="hwdock-card-<cardId>") wired
    by the SAME _wireSectionCollapse as every bar this file pins - a real
    arrow per card, per-id keys under the ledRasterPanelCollapsed_
    convention, one behaviour, one card at a time. The deep dock coverage
    (drags, glances, gear popovers) lives in tests/test_hardware_dock.py."""
    open_view(page, 'data-flow')
    ids = page.evaluate("""async () => {
        const mk = async (deviceId) => {
            const add = await (await fetch('/api/processors', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ deviceId }),
            })).json();
            return add.resolved[add.resolved.length - 1].id;
        };
        const a = await mk('brompton-sx40');
        const b = await mk('brompton-sx40');
        await window.app.refreshProcessors();
        const cardOf = (pid) => {
            const p = (window.app._processorsResolved || [])
                .find(x => x.id === pid);
            return p.slots.map(s => s.card).find(Boolean).id;
        };
        return { procs: [a, b], cards: [cardOf(a), cardOf(b)] };
    }""")
    page.wait_for_timeout(600)
    try:
        cards = page.evaluate("""(cardIds) => cardIds.map(cid => {
            const head = document.querySelector(
                `[data-lrd-sec="hwdock-card-${cid}"]`);
            if (!head) return { missing: cid };
            const box = head.parentElement;
            const arrow = head.querySelector('.lrd-sec-arrow');
            return {
                wired: !!head.dataset.lrdSecWired,
                arrowPainted: !!arrow && arrow.getClientRects().length > 0,
                key: box.dataset.lrdSecId || null,
            };
        })""", ids['cards'])
        for cid, card in zip(ids['cards'], cards):
            assert not card.get('missing'), (
                f'card {cid} built no dock section')
            assert card['wired'], (
                f'card {cid} not wired by the section machinery')
            assert card['arrowPainted'], f'card {cid} carries no live arrow'
            assert card['key'] == f'hwdock-card-{cid}', (
                f'card {cid} persists outside the ledRasterPanelCollapsed_ '
                f'convention: {card}')

        page.locator(
            f'[data-lrd-sec="hwdock-card-{ids["cards"][0]}"] '
            f'.lrd-sec-arrow').click()
        page.wait_for_timeout(100)
        folded = page.evaluate("""(cardIds) => cardIds.map(cid => {
            const head = document.querySelector(
                `[data-lrd-sec="hwdock-card-${cid}"]`);
            const box = head.parentElement;
            const body = box.querySelector(':scope > .lrd-sec-body');
            return {
                collapsed: getComputedStyle(body).display === 'none',
                bodyInDom: body.isConnected,
                headPainted: head.getClientRects().length > 0,
                stored: localStorage.getItem(
                    'ledRasterPanelCollapsed_hwdock-card-' + cid),
            };
        })""", ids['cards'])
        assert folded[0]['collapsed'], (
            f'the arrow did not fold the card: {folded[0]}')
        assert folded[0]['headPainted'], (
            f'the folded card lost its header - folded, a card must still '
            f'read as its one-line glance: {folded[0]}')
        assert folded[0]['bodyInDom'], (
            'the folded body left the DOM - collapse must hide, never detach')
        assert folded[0]['stored'] == '1', folded[0]
        assert not folded[1]['collapsed'], (
            f'folding one card took its neighbour: {folded[1]}')
    finally:
        # the shared server serves every module after this one
        page.evaluate("""async (ids) => {
            for (const pid of ids.procs) {
                await fetch(`/api/processors/${pid}`, { method: 'DELETE' });
            }
            for (const cid of ids.cards) {
                localStorage.removeItem(
                    'ledRasterPanelCollapsed_hwdock-card-' + cid);
            }
            await window.app.refreshProcessors();
        }""", ids)
