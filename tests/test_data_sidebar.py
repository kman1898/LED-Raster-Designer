"""The middle panels: a docked column that exists in exactly one view.

The left sidebar had no room left for the processor work Data view is about to
grow, so signal got its own panel between the left sidebar and the canvas, and
the port labelling UI moved into it. Power distribution - the home-run multis,
the splitters that gang circuits onto one of them, and the distros they land on
- ran out of the same room and got the second one, in the same slot, driven by
the same three tables (collapse in app-core.js initSidebarToggles, resize in
theme.js PANELS, view scoping in app-core.js updateViewSidebars).

What these tests pin, for BOTH panels:

* The panel is in layout in its own view and OUT of layout everywhere else -
  which means display:none rather than a zero-width collapse (a collapsed panel
  still takes a flex slot and still draws a border). The two never appear
  together.
* It collapses and expands on its own toggle, and the state survives a reload
  the same way the left and right sidebars' does.
* The editors really are inside it, the ids are still unique, and nothing was
  left behind in the left sidebar.
* Editing a field and pressing Tab still leaves focus in a real field after the
  rebuild that follows. This deliberately overlaps
  tests/test_label_editor_focus.py: moving the markup is precisely the change
  that could break _preserveEditorFocus.
* The distro list, which is project-level and blanks itself for nothing, is
  painted in Power view and nowhere else. Before the move it was hidden only by
  the Power Settings panel it happened to sit inside.
* Collapsing one panel does not move the others.

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


# One row per view-scoped middle panel - the same table the app itself is
# driven from, so a third panel is a row here rather than a copy of the file.
MIDDLE = {
    'data': {'sidebar': 'data-sidebar', 'toggle': 'data-sidebar-toggle',
             'mode': 'data-flow', 'label': 'Signal'},
    'power': {'sidebar': 'power-sidebar', 'toggle': 'power-sidebar-toggle',
              'mode': 'power', 'label': 'Power'},
}
ALL_VIEWS = ['pixel-map', 'cabinet-id', 'show-look', 'data-flow', 'power']
ABSENT = [(key, mode) for key, p in MIDDLE.items() for mode in ALL_VIEWS
          if mode != p['mode']]


# Build our OWN project through the real endpoints. The live server is shared
# with every other browser test file, and inheriting whatever the previous one
# left behind has produced "passes alone, fails together" twice in this repo.
#
# 4x4 of 128px cabinets is deliberate: it builds at least two ports, so the
# editor has a Port 1 Return for Tab to move INTO. On a screen small enough to
# need one port, Tab leaves the editor and the focus test proves nothing.
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
    // The editor sizes itself from _portsRequired, which is a client-side
    // computation - a layer fetched straight from the server carries none.
    app.updatePortCapacityDisplay();
    app.updatePortLabelEditor();
    if (window.canvasRenderer) window.canvasRenderer.render();
    return screen.id;
}"""


# The Power panel's three hosts only build rows once the screen has circuits,
# and the distro list only has rows once there is a distro. Driven through the
# real static fields rather than by writing the model, so the change handlers
# (and the deferred rebuild they schedule) are the things under test.
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
    app.refreshSocaRuns();
    app.refreshSplitterPanel();
    app.refreshDistroPanel();
    return { distros: app.getDistros().length,
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
            left: Math.round(r.left),
            right: Math.round(r.right),
        };
    };
    const toggle = (id) => {
        const b = document.getElementById(id);
        return b ? getComputedStyle(b).display !== 'none' : null;
    };
    return {
        data: read('data-sidebar'),
        power: read('power-sidebar'),
        left: read('left-sidebar'),
        right: read('right-sidebar'),
        canvas: read('canvas-container'),
        toggleShown: {
            data: toggle('data-sidebar-toggle'),
            power: toggle('power-sidebar-toggle'),
        },
    };
}"""


def open_view(page, mode):
    page.locator(f'[data-mode="{mode}"]').click()
    page.wait_for_timeout(400)


def state(page):
    return page.evaluate(STATE_JS)


def set_panel_collapsed(page, key, collapsed):
    """Drive the real toggle button, not the class, so the click handler and
    its localStorage write are the things under test."""
    if state(page)[key]['collapsed'] == collapsed:
        return
    page.locator(f'#{MIDDLE[key]["toggle"]}').click()
    page.wait_for_timeout(400)
    assert state(page)[key]['collapsed'] == collapsed


# ── one view each ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('key', sorted(MIDDLE))
def test_the_panel_is_in_layout_in_its_own_view(page, key):
    open_view(page, MIDDLE[key]['mode'])
    s = state(page)
    assert s[key]['displayed'], f"the {MIDDLE[key]['label']} panel is missing"
    assert s[key]['width'] > 0, f"in layout but zero width: {s[key]}"
    assert s['toggleShown'][key], "the panel is shown but its toggle is not"


@pytest.mark.parametrize('key,mode', ABSENT)
def test_the_panel_is_absent_from_every_other_view(page, key, mode):
    """The regression bar for both panels: anyone who never opens that view
    sees no change at all. Out of layout, not merely collapsed."""
    open_view(page, mode)
    s = state(page)
    label = MIDDLE[key]['label']
    assert not s[key]['displayed'], (
        f"the {label} panel is still in layout in {mode}: {s[key]}")
    assert s[key]['width'] == 0, f"it still takes width in {mode}: {s[key]}"
    assert not s['toggleShown'][key], (
        f"a toggle for a panel that is not there, in {mode}")


@pytest.mark.parametrize('mode', ALL_VIEWS)
def test_the_canvas_starts_where_the_visible_panels_end(page, mode):
    """A collapsed-but-present panel would leave its border behind, and two
    middle panels in layout at once would push the canvas twice."""
    open_view(page, mode)
    s = state(page)
    shown = [s[k] for k in MIDDLE if s[k]['displayed']]
    assert len(shown) <= 1, (
        f"more than one middle panel is in layout in {mode}: {s}")
    edge = shown[0]['right'] if shown else s['left']['right']
    assert abs(s['canvas']['left'] - edge) <= 1, (
        f"the canvas does not start at the last panel's edge in {mode}: "
        f"canvas left {s['canvas']['left']}, edge {edge}")


@pytest.mark.parametrize('key', sorted(MIDDLE))
def test_the_panel_sits_between_the_left_sidebar_and_the_canvas(page, key):
    open_view(page, MIDDLE[key]['mode'])
    s = state(page)
    assert s['left']['right'] <= s[key]['left'] + 1, (
        f"the {MIDDLE[key]['label']} panel is not right of the left sidebar: {s}")
    assert s[key]['right'] <= s['canvas']['left'] + 1, (
        f"the {MIDDLE[key]['label']} panel is not left of the canvas: {s}")


# ── Collapse ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize('key', sorted(MIDDLE))
def test_it_collapses_and_expands_on_its_own_toggle(page, key):
    open_view(page, MIDDLE[key]['mode'])
    set_panel_collapsed(page, key, True)
    # <= 1, not == 0: the theme keeps each docked panel's 1px inner border at
    # full width even when the panel itself is zero, so a collapsed panel is a
    # hairline seam. The left and right sidebars have always behaved this way
    # and these match them on purpose.
    assert state(page)[key]['width'] <= 1, "collapsed but still taking width"
    set_panel_collapsed(page, key, False)
    assert state(page)[key]['width'] > 100, "expanded but still not a panel"


@pytest.mark.parametrize('key', sorted(MIDDLE))
def test_the_collapsed_state_survives_a_reload(page, key):
    mode = MIDDLE[key]['mode']
    open_view(page, mode)
    set_panel_collapsed(page, key, True)

    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, mode)
    assert state(page)[key]['collapsed'], (
        f"the {MIDDLE[key]['label']} panel came back expanded after a reload")

    # And the other way round, so the test cannot pass on a panel that is
    # simply always collapsed.
    set_panel_collapsed(page, key, False)
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, mode)
    assert not state(page)[key]['collapsed'], (
        f"the {MIDDLE[key]['label']} panel came back collapsed after a reload")
    page.evaluate(RESET_JS)
    page.wait_for_timeout(600)


def test_the_two_middle_panels_collapse_independently(page):
    """They share a slot and are never both in layout, so a shared collapse key
    would look right until the user switched tabs."""
    open_view(page, 'data-flow')
    set_panel_collapsed(page, 'data', True)

    open_view(page, 'power')
    assert not state(page)['power']['collapsed'], (
        "collapsing Signal collapsed Power with it")
    set_panel_collapsed(page, 'power', False)

    open_view(page, 'data-flow')
    assert state(page)['data']['collapsed'], (
        "the Signal panel expanded itself while Power was being used")
    set_panel_collapsed(page, 'data', False)

    stored = page.evaluate(
        """() => ({ data: localStorage.getItem('ledRasterSidebarCollapsed_data'),
                    power: localStorage.getItem('ledRasterSidebarCollapsed_power') })""")
    assert stored['data'] is not None and stored['power'] is not None, (
        f"one of the panels is not persisting its own collapsed state: {stored}")


@pytest.mark.parametrize('key', sorted(MIDDLE))
def test_the_panels_in_a_view_collapse_independently(page, key):
    open_view(page, MIDDLE[key]['mode'])
    set_panel_collapsed(page, key, False)

    def collapse(toggle_id):
        page.locator(f'#{toggle_id}').click()
        page.wait_for_timeout(400)

    middle_toggle = MIDDLE[key]['toggle']

    collapse('left-sidebar-toggle')
    s = state(page)
    assert s['left']['collapsed'], "the left sidebar did not collapse"
    assert not s[key]['collapsed'], "collapsing left took the middle panel"
    assert not s['right']['collapsed'], "collapsing left took the right sidebar"

    collapse(middle_toggle)
    s = state(page)
    assert s[key]['collapsed'], "the middle panel did not collapse"
    assert not s['right']['collapsed'], "collapsing it took the right sidebar"

    collapse('right-sidebar-toggle')
    assert state(page)['right']['collapsed'], "the right sidebar did not collapse"

    # Back out, one at a time, and each must come back alone.
    collapse('left-sidebar-toggle')
    s = state(page)
    assert not s['left']['collapsed'], "the left sidebar did not expand"
    assert s[key]['collapsed'], "expanding left dragged the middle panel back"
    assert s['right']['collapsed'], "expanding left dragged the right sidebar back"

    collapse(middle_toggle)
    collapse('right-sidebar-toggle')
    s = state(page)
    assert not s[key]['collapsed'] and not s['right']['collapsed'], s


# ── the editors came with the panels ──────────────────────────────────────

PORT_LABEL_IDS = [
    'port-label-template-primary',
    'port-label-template-return',
    'port-label-bulk-primary',
    'port-label-bulk-return',
    'port-label-apply-selected',
    'port-label-clear-selected',
    'port-label-select-all',
    'port-label-deselect-all',
    'port-label-list',
]

# The three hosts app-power.js builds into, plus the circuit label editor
# that joined them: naming a circuit now starts at the distro and runs down
# through the multi, so the whole chain reads in one panel.
#
# They were MOVED, not copied: a second element with one of these ids would
# split document.getElementById from the focus-restore lookup and break
# editing without failing anything. Two circuit-label editors bound to one set
# of data-lrd-field keys is the sharper version of the same bug - they would
# fight over the focus restore, and you would type into one while the other
# held the state.
POWER_HOST_IDS = [
    'power-soca-runs', 'power-splitters', 'power-distros',
    'power-label-template', 'power-label-bulk',
    'power-label-apply-selected', 'power-label-clear-selected',
    'power-label-select-all', 'power-label-deselect-all',
    'power-label-list',
]

MOVED = ([('data', element_id) for element_id in PORT_LABEL_IDS]
         + [('power', element_id) for element_id in POWER_HOST_IDS])


@pytest.mark.parametrize('key,element_id', MOVED)
def test_the_markup_moved_whole_and_kept_its_ids(page, key, element_id):
    open_view(page, MIDDLE[key]['mode'])
    found = page.evaluate(
        """([id, sidebar]) => {
            const all = document.querySelectorAll('[id="' + id + '"]');
            const inPanel = document.querySelectorAll(
                '#' + sidebar + ' [id="' + id + '"]').length;
            const inLeft = document.querySelectorAll(
                '#left-sidebar [id="' + id + '"]').length;
            return { total: all.length, inPanel, inLeft };
        }""", [element_id, MIDDLE[key]['sidebar']])
    assert found['total'] == 1, (
        f"#{element_id} is not unique in the document: {found}")
    assert found['inPanel'] == 1, (
        f"#{element_id} is not in the {MIDDLE[key]['label']} panel")
    assert found['inLeft'] == 0, f"#{element_id} was left in the left sidebar"


def test_the_editor_builds_its_rows_inside_the_signal_panel(page):
    open_view(page, 'data-flow')
    page.wait_for_timeout(300)
    fields = page.evaluate(
        """() => [...document.querySelectorAll('#data-sidebar [data-lrd-field]')]
               .map(el => el.dataset.lrdField)""")
    assert 'port-primary-1' in fields, f"no Port 1 Primary field: {fields}"
    assert 'port-return-1' in fields, (
        f"no Port 1 Return field - Tab out of Primary would leave the editor "
        f"and the focus test below would prove nothing: {fields}")


def test_the_power_hosts_build_their_rows_inside_the_power_panel(page):
    open_view(page, 'power')
    seeded = page.evaluate(POWER_SEED_JS)
    page.wait_for_timeout(600)
    assert seeded['circuits'] > 0, f"the test screen drew no circuits: {seeded}"
    assert seeded['distros'] > 0, f"no distro was added: {seeded}"
    built = page.evaluate(
        """() => {
            const inside = (host) => document.querySelectorAll(
                '#power-sidebar #' + host + ' *').length;
            window.app.updatePowerLabelEditor();
            return {
                soca: inside('power-soca-runs'),
                splitters: inside('power-splitters'),
                distros: inside('power-distros'),
                labels: inside('power-label-list'),
                fields: [...document.querySelectorAll(
                    '#power-sidebar [data-lrd-field]')].map(
                        el => el.dataset.lrdField),
                leftFields: [...document.querySelectorAll(
                    '#left-sidebar [data-lrd-field]')].map(
                        el => el.dataset.lrdField),
            };
        }""")
    assert built['soca'] > 0, f"the soca host built nothing: {built}"
    assert built['splitters'] > 0, f"the splitter host built nothing: {built}"
    assert built['distros'] > 0, f"the distro host built nothing: {built}"
    assert built['labels'] > 0, f"the circuit label editor built nothing: {built}"
    assert 'power-distro-add' in built['fields'], (
        f"the distro controls are not in the Power panel: {built['fields']}")
    assert any(f.startswith('power-soca-length-') for f in built['fields']), (
        f"no soca length field in the Power panel: {built['fields']}")
    assert any(f.startswith('power-soca-name-') for f in built['fields']), (
        f"no multi name field in the Power panel: {built['fields']}")
    assert any(f.startswith('power-label-') for f in built['fields']), (
        f"no circuit label field in the Power panel: {built['fields']}")
    # The rows too, not just the markup they build into: a copy of the editor
    # left behind in the left sidebar would answer to the same
    # data-lrd-field keys and fight this one for the focus restore.
    assert not [f for f in built['leftFields'] if f.startswith('power-label-')], (
        f"a circuit label editor is still building in the left sidebar: "
        f"{built['leftFields']}")


# ── the distro list is project-level and blanks itself for nothing ────────

PAINTED_JS = """() => {
    const host = document.getElementById('power-distros');
    const rows = [...document.querySelectorAll('.power-distro-row')];
    return {
        hostPainted: !!(host && host.offsetParent),
        rowsInDom: rows.length,
        rowsPainted: rows.filter(r => r.getClientRects().length > 0).length,
    };
}"""


def test_the_distro_list_is_painted_in_power_view(page):
    open_view(page, 'power')
    page.evaluate(POWER_SEED_JS)
    page.wait_for_timeout(600)
    painted = page.evaluate(PAINTED_JS)
    assert painted['hostPainted'], f"the distro host is not painted: {painted}"
    assert painted['rowsPainted'] > 0, f"no distro rows are drawn: {painted}"


@pytest.mark.parametrize('mode', ['pixel-map', 'cabinet-id', 'show-look',
                                  'data-flow'])
def test_the_distro_list_does_not_render_outside_power_view(page, mode):
    """refreshDistroPanel never blanks itself - the list is project-level, so
    there is no layer it is wrong for. Before the move it was hidden only by
    the Power Settings panel it happened to sit inside; take that ancestor
    away without replacing it and the distros draw on every tab."""
    open_view(page, 'power')
    page.evaluate(POWER_SEED_JS)
    page.wait_for_timeout(600)
    assert page.evaluate(PAINTED_JS)['rowsPainted'] > 0, (
        "the fixture built no distro rows, so this would prove nothing")

    open_view(page, mode)
    painted = page.evaluate(PAINTED_JS)
    assert not painted['hostPainted'], (
        f"the distro host is still painted in {mode}: {painted}")
    assert painted['rowsPainted'] == 0, (
        f"distro rows are drawn in {mode}: {painted}")


# ── focus survives the rebuilds ───────────────────────────────────────────

FOCUS_JS = """() => {
    const a = document.activeElement;
    return {
        tag: a ? a.tagName : null,
        id: a ? (a.id || null) : null,
        key: (a && a.dataset) ? (a.dataset.lrdField || null) : null,
        isBody: a === document.body,
        inPanel: !!(a && a.closest && a.closest('#data-sidebar')),
        inPowerPanel: !!(a && a.closest && a.closest('#power-sidebar')),
        stamped: !!(a && a.__stamp),
    };
}"""


def test_typing_a_label_and_pressing_tab_keeps_focus_in_a_real_field(page):
    """The editor wipes itself with innerHTML = '' on every server round-trip,
    so the field Tab just moved into is destroyed under the user's fingers.
    _preserveEditorFocus (app-power.js) restores it by data-lrd-field key -
    moving the markup is exactly what could have broken that."""
    open_view(page, 'data-flow')
    page.evaluate("""() => {
        const l = window.app.currentLayer;
        l.portLabelOverridesPrimary = {};
        l.portLabelOverridesReturn = {};
        window.app.updatePortLabelEditor();
    }""")
    page.wait_for_timeout(200)

    # Stamp the current fields. Element identity does not survive a rebuild,
    # so a still-stamped field afterwards would mean no rebuild happened and
    # the focus assertion would be passing for the wrong reason.
    stamped = page.evaluate(
        """() => {
            const els = document.querySelectorAll('#port-label-list input');
            els.forEach(el => { el.__stamp = 1; });
            return els.length;
        }""")
    assert stamped >= 2, f"the editor built no fields to test: {stamped}"

    page.evaluate(
        """() => document.querySelector(
               '[data-lrd-field="port-primary-1"]').focus()""")
    page.keyboard.type("SIG-A")
    page.keyboard.press("Tab")
    assert page.evaluate(FOCUS_JS)['key'] == 'port-return-1', (
        "Tab did not move to Port 1 Return - the moved markup changed the "
        "tab order inside the editor")

    page.wait_for_function(
        """() => {
            const el = document.querySelector('[data-lrd-field="port-return-1"]');
            return !!el && !el.__stamp;
        }""",
        timeout=5000,
    )
    after = page.evaluate(FOCUS_JS)
    assert not after['isBody'], (
        f"focus fell to <body> after the rebuild: {after}")
    assert after['tag'] == 'INPUT', f"focus left the editor entirely: {after}"
    assert after['key'] == 'port-return-1', f"focus moved elsewhere: {after}"
    assert after['inPanel'], (
        f"focus is outside the Signal panel, so the field it landed on is not "
        f"the moved editor's: {after}")
    assert not after['stamped'], (
        "the editor never rebuilt, so this proved nothing - the fixture or "
        "the round-trip changed")

    stored = page.evaluate(
        "() => window.app.currentLayer.portLabelOverridesPrimary")
    assert stored.get('1') == 'SIG-A', (
        f"the edit did not survive the move: {stored}")


def test_tabbing_out_of_the_last_static_power_field_lands_somewhere_real(page):
    """Watts per Panel used to be followed by the soca host; the hosts are in
    the Power panel now, so Tab walks on to the Flow Pattern buttons under it
    instead. Either way its change handler schedules a rebuild of all three
    hosts, and an inline one would have destroyed the stop Tab was moving
    into."""
    open_view(page, 'power')
    page.evaluate(POWER_SEED_JS)
    page.wait_for_timeout(600)

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
            const sidebar = a.closest('#left-sidebar') ? 'left'
                : a.closest('#power-sidebar') ? 'power' : 'elsewhere';
            return { sidebar, tag: a.tagName, cls: a.className,
                     visible: a.getClientRects().length > 0 };
        }""")
    assert landed['visible'], f"Tab landed on something not drawn: {landed}"
    assert landed['sidebar'] in ('left', 'power'), (
        f"Tab left the Power UI entirely: {landed}")
    assert page.evaluate(
        "() => parseFloat(window.app.currentLayer.panelWatts)") == 450, (
        "the edit did not commit when focus left the field")


def test_editing_a_distro_name_and_tabbing_keeps_focus_in_a_real_control(page):
    """The distro rows rebuild synchronously from their own change handlers, so
    the restate is deferred one macrotask and the rebuild that follows goes
    through _preserveEditorFocus. That restore is a document-global
    [data-lrd-field] lookup, which is why the rows kept working from a new
    parent - this proves it rather than assuming it."""
    open_view(page, 'power')
    page.evaluate(POWER_SEED_JS)
    page.wait_for_timeout(600)

    distro_id = page.evaluate("() => window.app.getDistros()[0].id")
    name_key = f'distro-name-{distro_id}'
    del_key = f'distro-del-{distro_id}'

    stamped = page.evaluate(
        """() => {
            const els = document.querySelectorAll('#power-distros input, '
                + '#power-distros button');
            els.forEach(el => { el.__stamp = 1; });
            return els.length;
        }""")
    assert stamped >= 2, f"the distro panel built no controls to test: {stamped}"

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
        }""", arg=del_key, timeout=5000)

    after = page.evaluate(FOCUS_JS)
    assert not after['isBody'], (
        f"focus fell to <body> after the distro rebuild: {after}")
    assert after['key'] == del_key, (
        f"focus is not back on the row's ✕ button: {after}")
    assert after['inPowerPanel'], (
        f"focus is outside the Power panel, so the control it landed on is not "
        f"the moved editor's: {after}")
    assert not after['stamped'], (
        "the distro panel never rebuilt, so this proved nothing")

    assert page.evaluate(
        "() => window.app.getDistros()[0].name") == 'BEACH 1', (
        "the distro rename did not survive the move")


# ── collapsible sections: the ▾ works everywhere it appears ───────────────
#
# Every titled section bar carried a decorative ▾ (theme.css ::after) that
# did nothing. It is now a real arrow button with ONE behaviour everywhere
# (user spec, exact): a single click on the ARROW toggles the section, a
# DOUBLE-click anywhere on the header does the same, and a single click on
# the header does NOTHING - stray clicks are harmless. State persists per
# section (ledRasterPanelCollapsed_<id>), survives a reload, and is
# independent of the sidebar-level collapse. The body hides but never
# leaves the DOM, and a focus restore into a folded section auto-expands
# it. The Power panel's generated block headings (soca / splitters /
# distros / circuit labels) are wired by the same mechanism at every
# rebuild.

# (view, panel title) for the headers the user named; the same wiring
# reaches every other .panel-header for free.
NAMED_HEADERS = [
    ('data-flow', 'Data Settings'),
    ('data-flow', 'Processors'),
    ('data-flow', 'Port Assignment'),
    ('data-flow', 'Port Labels'),
    ('power', 'Power Distribution'),
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


@pytest.mark.parametrize('mode,title', [('data-flow', 'Port Labels'),
                                        ('power', 'Power Distribution')])
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
    hdr = header_of(page, 'Port Labels')
    hdr.locator('.lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert header_state(page, 'Port Labels')['collapsed'] is True
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(2000)
    open_view(page, 'data-flow')
    s = header_state(page, 'Port Labels')
    assert s['collapsed'] is True, (
        f"Port Labels came back expanded after a reload: {s}")
    header_of(page, 'Port Labels').locator('.lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert header_state(page, 'Port Labels')['collapsed'] is False


POWER_BLOCK_JS = """(hostId) => {
    const host = document.getElementById(hostId);
    if (!host) return null;
    const head = host.querySelector(':scope > .lrd-sec-head');
    const body = host.querySelector(':scope > .lrd-sec-body');
    const arrow = host.querySelector('.lrd-sec-arrow');
    return {
        wired: !!(head && body && arrow),
        collapsed: body ? getComputedStyle(body).display === 'none' : null,
        bodyInDom: !!body && body.isConnected,
    };
}"""


def test_the_power_blocks_collapse_and_survive_their_rebuilds(page):
    """The soca / splitter / distro blocks rebuild with innerHTML on every
    refresh; the generation wires the same collapse and re-applies the
    persisted state, so a folded block stays folded across a rebuild."""
    open_view(page, 'power')
    page.evaluate(POWER_SEED_JS)
    page.wait_for_timeout(600)
    for host in ('power-soca-runs', 'power-splitters', 'power-distros'):
        s = page.evaluate(POWER_BLOCK_JS, host)
        assert s and s['wired'], f"#{host} built no collapsible heading: {s}"
        assert s['collapsed'] is False, f"#{host} started collapsed: {s}"
    # the static Circuit Labels block is wired by the same init
    assert page.evaluate("""() => {
        const head = document.querySelector('[data-lrd-sec="power-circuit-labels"]');
        return !!(head && head.querySelector('.lrd-sec-arrow'));
    }"""), "the Circuit Labels block has no collapse arrow"

    page.locator('#power-soca-runs .lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert page.evaluate(POWER_BLOCK_JS, 'power-soca-runs')['collapsed'] is True
    survived = page.evaluate("""async () => {
        window.app.refreshSocaRuns();
        await new Promise(r => setTimeout(r, 50));
        const body = document.querySelector('#power-soca-runs > .lrd-sec-body');
        return getComputedStyle(body).display === 'none';
    }""")
    assert survived, "a rebuild re-expanded the folded soca block"
    page.locator('#power-soca-runs .lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert page.evaluate(POWER_BLOCK_JS, 'power-soca-runs')['collapsed'] is False


def test_focus_restore_into_a_collapsed_section_expands_it(page):
    """The stated rule: a field the app programmatically focuses (the
    _preserveEditorFocus restore after a rebuild) must be visible, so the
    folded section it lives in opens rather than swallowing the focus."""
    open_view(page, 'power')
    page.evaluate(POWER_SEED_JS)
    page.wait_for_timeout(600)
    out = page.evaluate("""async () => {
        const app = window.app;
        const host = document.getElementById('power-soca-runs');
        // The soca fields live inside tiles now, so the field a user would
        // be standing in is one whose tile is open - open it the way they
        // would, through the face.
        const tile = host.querySelector('.lrd-tile');
        if (tile && !tile.classList.contains('lrd-tile-open')) {
            tile.querySelector(':scope > .lrd-tile-face').click();
        }
        const el = host.querySelector('input[data-lrd-field]');
        if (!el) return { skipped: true };
        el.focus();
        app._preserveEditorFocus();           // captures key + schedules restore
        app._setSectionCollapsed(host, true); // fold before the restore lands
        if (document.activeElement) document.activeElement.blur();
        await new Promise(r => setTimeout(r, 20));
        const body = host.querySelector(':scope > .lrd-sec-body');
        const reopened = getComputedStyle(body).display !== 'none';
        const focusedBack = document.activeElement === el;
        return { reopened, focusedBack,
                 stored: localStorage.getItem('ledRasterPanelCollapsed_power-soca-runs') };
    }""")
    assert not out.get('skipped'), "the soca panel built no field to focus"
    assert out['reopened'], (
        f"the restore left the section folded around the focused field: {out}")
    assert out['focusedBack'], f"focus was not restored into the field: {out}"
    assert out['stored'] == '0', (
        f"the auto-expansion must persist, or the next rebuild folds the "
        f"field away again: {out}")


def test_section_collapse_is_independent_of_the_sidebar_collapse(page):
    """Folding the Power panel and reopening it must not touch a folded
    section inside it - the two states live under different keys."""
    open_view(page, 'power')
    page.evaluate(POWER_SEED_JS)
    page.wait_for_timeout(600)
    page.locator('#power-distros .lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert page.evaluate(POWER_BLOCK_JS, 'power-distros')['collapsed'] is True
    set_panel_collapsed(page, 'power', True)
    set_panel_collapsed(page, 'power', False)
    s = page.evaluate(POWER_BLOCK_JS, 'power-distros')
    assert s['collapsed'] is True, (
        f"collapsing the sidebar re-expanded the section inside it: {s}")
    keys = page.evaluate("""() => ({
        section: localStorage.getItem('ledRasterPanelCollapsed_power-distros'),
        sidebar: localStorage.getItem('ledRasterSidebarCollapsed_power'),
    })""")
    assert keys['section'] == '1' and keys['sidebar'] == '0', keys
    page.locator('#power-distros .lrd-sec-arrow').click()
    page.wait_for_timeout(100)
    assert page.evaluate(POWER_BLOCK_JS, 'power-distros')['collapsed'] is False


def test_the_processor_cards_fold_by_the_same_machinery(page):
    """The generated per-processor heads in the Signal panel are wired by the
    SAME _wireSectionCollapse as every bar this file pins: a real arrow per
    card, per-id keys under the ledRasterPanelCollapsed_ convention, one
    behaviour. Folded, a card is its one-line summary; the deep coverage
    (persistence, focus restore, the chooser reveal) lives in
    tests/test_processor_panel.py."""
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
        return [a, b];
    }""")
    page.wait_for_timeout(600)
    try:
        cards = page.evaluate("""(ids) => ids.map(pid => {
            const head = document.querySelector(
                `[data-lrd-sec="processor-${pid}"]`);
            const box = head && head.parentElement;
            const arrow = head && head.querySelector('.lrd-sec-arrow');
            return {
                wired: !!(head && head.dataset.lrdSecWired),
                arrowPainted: !!arrow && arrow.getClientRects().length > 0,
                key: box ? box.dataset.lrdSecId : null,
            };
        })""", ids)
        for pid, card in zip(ids, cards):
            assert card['wired'], f'{pid} not wired by the section machinery'
            assert card['arrowPainted'], f'{pid} carries no live arrow'
            assert card['key'] == f'processor-{pid}', (
                f'{pid} persists outside the ledRasterPanelCollapsed_ '
                f'convention: {card}')

        page.locator(
            f'[data-lrd-sec="processor-{ids[0]}"] .lrd-sec-arrow').click()
        page.wait_for_timeout(100)
        folded = page.evaluate("""(ids) => ids.map(pid => {
            const head = document.querySelector(
                `[data-lrd-sec="processor-${pid}"]`);
            const box = head.parentElement;
            const body = box.querySelector(':scope > .lrd-sec-body');
            const sum = head.querySelector('.lrd-proc-summary');
            return {
                collapsed: getComputedStyle(body).display === 'none',
                bodyInDom: body.isConnected,
                summaryPainted: !!sum && sum.getClientRects().length > 0,
                stored: localStorage.getItem(
                    'ledRasterPanelCollapsed_processor-' + pid),
            };
        })""", ids)
        assert folded[0]['collapsed'] and folded[0]['summaryPainted'], (
            f'the arrow did not fold the card to its summary: {folded[0]}')
        assert folded[0]['bodyInDom'], (
            'the folded body left the DOM - collapse must hide, never detach')
        assert folded[0]['stored'] == '1', folded[0]
        assert not folded[1]['collapsed'], (
            f'folding one card took its neighbour: {folded[1]}')
    finally:
        # the shared server serves every module after this one
        page.evaluate("""async (ids) => {
            for (const pid of ids) {
                await fetch(`/api/processors/${pid}`, { method: 'DELETE' });
                localStorage.removeItem(
                    'ledRasterPanelCollapsed_processor-' + pid);
            }
            await window.app.refreshProcessors();
        }""", ids)
