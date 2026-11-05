"""The Names switch (Screens / Group / Both) per GROUP, per tab.

The owner's ruling of 2026-11-04: "depending on which group is selected, I
need to be able to individually change screens, group or both per group".

  * Each group keeps its own value for each of the five tabs, in
    group.nameDisplayByView. The canvas and the binder read it through one
    helper, app.groupNameDisplayFor(view, group).
  * The switch acts on the selection: a member or the whole group sets that
    group, several groups selected are set together, and with no group in
    the selection the Names row hides. Groups that differ light no button.
  * Old shows: every group starts on the tab's show-wide value
    (groupNameDisplayByView, else groupNameDisplay), client and server.
  * Each change is one undo step, "Change Name Display".
  * Binder sheets follow each group's own Data and Power value.

Several groups are picked the way several screens are: Cmd/Ctrl adds a group's
header to the selection and Shift ranges to it (1.6.0 QA, beta.6: the header's
click replaced the selection whatever was held).

Two 4 x 3 walls make WALL (WALL-L + WALL-R), two more make SIDE (SIDE-L +
SIDE-R), and LONE stands alone. Each pair routes as one screen on both sides.

Run locally:
    python -m pytest tests/test_names_per_group.py -v --browser chromium
"""

import json
import os
import sys

import pytest

from conftest import settled

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

VIEWS = ['pixel-map', 'cabinet-id', 'data-flow', 'power', 'show-look']


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    delete proj.groupNameDisplay; delete proj.groupNameDisplayByView;
    await j('PUT', '/api/project', proj);
    const add = (body) => j('POST', '/api/layer/add', body);
    const wall = {columns: 4, rows: 3, cabinet_width: 200, cabinet_height: 200,
                  powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
                  powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
                  processorType: 'novastar-armor'};
    await add({...wall, name: 'WALL-L'});
    await add({...wall, name: 'WALL-R', offset_x: 800});
    await add({...wall, name: 'SIDE-L', offset_y: 1000});
    await add({...wall, name: 'SIDE-R', offset_x: 800, offset_y: 1000});
    await add({name: 'LONE', columns: 3, rows: 2, cabinet_width: 128, cabinet_height: 128,
               powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
               powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor', offset_x: 2000});
    let p = await j('GET', '/api/project');
    const by = (n) => p.layers.find(l => l.name === n);
    const [a1, a2, b1, b2] = ['WALL-L', 'WALL-R', 'SIDE-L', 'SIDE-R'].map(by);
    a1.group_id = a2.group_id = 'g1';
    b1.group_id = b2.group_id = 'g2';
    p.groups = [{id: 'g1', name: 'WALL', layer_ids: [a1.id, a2.id]},
                {id: 'g2', name: 'SIDE', layer_ids: [b1.id, b2.id]}];
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('names_per_group_setup');
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Names Per Group Seed');
    const L = (n) => app.project.layers.find(l => l.name === n);
    return { routed: ['WALL-R', 'SIDE-R'].map(n => app.isServedByPeerRouting(L(n), 'data')
                                         && app.isServedByPeerRouting(L(n), 'power')) };
}"""

# In-page helpers: select screens by name, click a Names button, read what
# the canvas draws, read the rows.
HELPERS_JS = """() => {
    window.__npg = {
        L(n) { return window.app.project.layers.find(l => l.name === n); },
        G(id) { return window.app.resolveGroup(id); },
        select(names) {
            const app = window.app;
            const ls = names.map(n => this.L(n));
            app.selectLayer(ls[0]);
            if (ls.length > 1) {
                app.selectedLayerIds = new Set(ls.map(l => l.id));
                app.updatePortCapacityDisplay();
            }
        },
        click(view, value) {
            document.querySelector(
                `.name-display-btn[data-name-view="${view}"][data-name-display="${value}"]`).click();
        },
        rows() {
            const out = {};
            document.querySelectorAll('.name-display-row').forEach(row => {
                const view = row.querySelector('.name-display-btn').dataset.nameView;
                out[view] = {
                    shown: row.style.display !== 'none',
                    mixed: row.getAttribute('data-mixed') === '1',
                    active: [...row.querySelectorAll('.name-display-btn.active')]
                        .map(b => b.dataset.nameDisplay),
                };
            });
            return out;
        },
        values(id) {
            const app = window.app, g = this.G(id);
            const out = {};
            for (const v of ['pixel-map', 'cabinet-id', 'data-flow', 'power', 'show-look']) {
                out[v] = app.groupNameDisplayFor(v, g);
            }
            return out;
        },
        drawn(view) {
            const r = window.canvasRenderer, ctx = r.ctx;
            const was = r.viewMode;
            r.viewMode = view;
            const original = ctx.fillText;
            const texts = [];
            ctx.fillText = function (t, x, y, w) {
                texts.push(String(t));
                return original.call(ctx, t, x, y, w);
            };
            try { r.render(); } finally { ctx.fillText = original; r.viewMode = was; r.render(); }
            return texts;
        },
    };
    return true;
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
        'scope': {'kind': 'show'}, 'cover': False, 'pull': True, 'hardware': False,
        'wiring': False, 'titleBlock': True}


def _route_native_dialogs(context):
    """Never a real Windows dialog on the owner's desktop."""
    cancel = json.dumps({'ok': False, 'cancelled': True, 'unavailable': False})
    for path in ('save-file', 'open-file', 'select-directory'):
        context.route(f'**/api/native-dialog/{path}',
                      lambda route: route.fulfill(status=200, content_type='application/json',
                                                  body=cancel))


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    _route_native_dialogs(context)
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    seeded = pg.evaluate(SEED_JS)
    # the fixture's premise: each pair routes as one wall on both sides
    assert seeded['routed'] == [True, True], seeded
    pg.evaluate(HELPERS_JS)
    pg.evaluate("() => { document.querySelector('[data-mode=\"pixel-map\"]').click(); }")
    pg.wait_for_timeout(300)
    yield pg, errors
    context.close()


def _reset(pg):
    """Both groups back to no value of their own, nothing show-wide, the
    selection on WALL-L, a fresh history."""
    pg.evaluate("""() => {
        const app = window.app;
        for (const g of app.project.groups) delete g.nameDisplayByView;
        delete app.project.groupNameDisplay;
        delete app.project.groupNameDisplayByView;
        window.__npg.select(['WALL-L']);
        app.resetHistory('Names Reset');
        app.refreshNameDisplayButtons();
    }""")


def _set_wall_group_side_screens(pg):
    """Both groups to Both in one click, then WALL to Group and SIDE to
    Screens on Pixel Map, one group at a time."""
    return pg.evaluate("""() => {
        const h = window.__npg, app = window.app;
        const steps = [];
        h.select(['WALL-L', 'SIDE-L']);
        h.click('pixel-map', 'both');
        steps.push({ wall: h.values('g1'), side: h.values('g2'), rows: h.rows(),
                     action: app.history[app.historyIndex].action, index: app.historyIndex });
        h.select(['WALL-R']);
        h.click('pixel-map', 'group');
        steps.push({ wall: h.values('g1'), side: h.values('g2'), rows: h.rows(),
                     action: app.history[app.historyIndex].action, index: app.historyIndex });
        h.select(['SIDE-L']);
        h.click('pixel-map', 'screens');
        steps.push({ wall: h.values('g1'), side: h.values('g2'), rows: h.rows(),
                     action: app.history[app.historyIndex].action, index: app.historyIndex });
        return steps;
    }""")


def test_each_group_takes_its_own_value_from_the_selection(page):
    pg, errors = page
    _reset(pg)
    both, wall_group, side_screens = _set_wall_group_side_screens(pg)
    default = {v: 'group' for v in VIEWS}
    # a multi-group selection sets both groups, in one undo step
    assert both['wall'] == {**default, 'pixel-map': 'both'}, both
    assert both['side'] == {**default, 'pixel-map': 'both'}, both
    assert both['action'] == 'Change Name Display' and both['index'] == 1, both
    assert both['rows']['pixel-map'] == {'shown': True, 'mixed': False, 'active': ['both']}, both
    # selecting one member of WALL sets WALL alone
    assert wall_group['wall']['pixel-map'] == 'group', wall_group
    assert wall_group['side']['pixel-map'] == 'both', wall_group
    assert wall_group['index'] == 2, wall_group
    # and one member of SIDE sets SIDE alone
    assert side_screens['wall'] == default, side_screens
    assert side_screens['side'] == {**default, 'pixel-map': 'screens'}, side_screens
    assert side_screens['index'] == 3 and side_screens['action'] == 'Change Name Display', side_screens
    assert side_screens['rows']['pixel-map']['active'] == ['screens'], side_screens
    # the other tabs keep their own values, on both groups
    for v in VIEWS[1:]:
        assert side_screens['rows'][v] == {'shown': True, 'mixed': False, 'active': ['group']}, (v, side_screens)
    # the show-wide fields are not touched by the switch
    show = pg.evaluate("() => [window.app.project.groupNameDisplay, window.app.project.groupNameDisplayByView]")
    assert show == [None, None], show
    assert not errors, errors


def test_the_canvas_draws_each_group_by_its_own_value(page):
    pg, errors = page
    _reset(pg)
    _set_wall_group_side_screens(pg)
    out = pg.evaluate("""() => ({ pixel: window.__npg.drawn('pixel-map'),
                                  cabinet: window.__npg.drawn('cabinet-id') })""")
    pixel, cabinet = out['pixel'], out['cabinet']
    # Pixel Map: WALL by its group name, SIDE by its screens' names
    assert 'WALL' in pixel and 'WALL-L' not in pixel and 'WALL-R' not in pixel, pixel
    assert 'SIDE-L' in pixel and 'SIDE-R' in pixel and 'SIDE' not in pixel, pixel
    # Cabinet ID keeps its own value, Group, for both
    assert 'WALL' in cabinet and 'SIDE' in cabinet, cabinet
    assert not any(n in cabinet for n in ('WALL-L', 'WALL-R', 'SIDE-L', 'SIDE-R')), cabinet
    # an ungrouped screen keeps its name either way
    assert 'LONE' in pixel and 'LONE' in cabinet
    assert not errors, errors


def test_groups_that_differ_light_no_button_and_one_click_sets_both(page):
    pg, errors = page
    _reset(pg)
    _set_wall_group_side_screens(pg)
    out = pg.evaluate("""() => {
        const h = window.__npg, app = window.app;
        h.select(['WALL-L', 'SIDE-R']);
        const mixed = h.rows();
        const index = app.historyIndex;
        h.click('pixel-map', 'both');
        return { mixed, after: h.rows(), wall: h.values('g1'), side: h.values('g2'),
                 steps: app.historyIndex - index };
    }""")
    assert out['mixed']['pixel-map'] == {'shown': True, 'mixed': True, 'active': []}, out
    assert out['mixed']['power'] == {'shown': True, 'mixed': False, 'active': ['group']}, out
    assert out['after']['pixel-map'] == {'shown': True, 'mixed': False, 'active': ['both']}, out
    assert out['wall']['pixel-map'] == 'both' and out['side']['pixel-map'] == 'both', out
    assert out['steps'] == 1, out
    assert not errors, errors


# ── picking groups from their headers ─────────────────────────────────────

def _header(group_id):
    return f'#layers-list .screen-group[data-group-id="{group_id}"] .screen-group-info'


def _selected(pg):
    return pg.evaluate("""() => [...window.app.selectedLayerIds]
        .map(id => window.app.project.layers.find(l => l.id === id).name).sort()""")


def _lit(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('#layers-list .screen-group.active')]
        .map(el => el.dataset.groupId).sort()""")


def _lone_row(pg):
    lone = pg.evaluate("() => window.__npg.L('LONE').id")
    return f'#layers-list .layer-item[data-layer-id="{lone}"] .layer-info'


def test_ctrl_on_a_group_header_adds_it_and_one_click_sets_both(page):
    pg, errors = page
    _reset(pg)
    pg.locator(_header('g1')).click()
    assert _selected(pg) == ['WALL-L', 'WALL-R']
    pg.locator(_header('g2')).click(modifiers=['Control'])
    assert _selected(pg) == ['SIDE-L', 'SIDE-R', 'WALL-L', 'WALL-R']
    assert _lit(pg) == ['g1', 'g2']
    index = pg.evaluate("() => window.app.historyIndex")
    pg.locator('.name-display-btn[data-name-view="pixel-map"][data-name-display="both"]').click()
    out = pg.evaluate("() => ({ wall: window.__npg.values('g1'), side: window.__npg.values('g2'),"
                      " rows: window.__npg.rows(), index: window.app.historyIndex })")
    assert out['wall']['pixel-map'] == 'both' and out['side']['pixel-map'] == 'both', out
    assert out['rows']['pixel-map'] == {'shown': True, 'mixed': False, 'active': ['both']}, out
    assert out['index'] == index + 1, out
    # one undo takes both back, and the selection stands
    pg.keyboard.press('Control+z')
    settled(pg, lambda: pg.evaluate("() => window.__npg.values('g1')['pixel-map']"), lambda v: v != 'both')
    assert pg.evaluate("() => window.__npg.values('g2')['pixel-map']") != 'both'
    assert _selected(pg) == ['SIDE-L', 'SIDE-R', 'WALL-L', 'WALL-R']
    assert not errors, errors


def test_ctrl_on_a_selected_group_header_takes_it_out(page):
    pg, errors = page
    _reset(pg)
    pg.locator(_header('g1')).click()
    pg.locator(_header('g2')).click(modifiers=['Control'])
    pg.locator(_header('g1')).click(modifiers=['Control'])
    assert _selected(pg) == ['SIDE-L', 'SIDE-R']
    assert _lit(pg) == ['g2']
    assert pg.evaluate("() => window.app.currentLayer.name") in ('SIDE-L', 'SIDE-R')
    pg.locator(_header('g2')).click(modifiers=['Control'])
    assert _selected(pg) == []
    assert pg.evaluate("() => window.app.currentLayer") is None
    assert pg.evaluate("() => window.__npg.rows()['pixel-map'].shown") is False
    assert not errors, errors


def test_ctrl_on_a_header_finishes_a_group_half_selected(page):
    pg, errors = page
    _reset(pg)                              # WALL-L alone
    pg.locator(_header('g1')).click(modifiers=['Control'])
    assert _selected(pg) == ['WALL-L', 'WALL-R']
    assert not errors, errors


def test_ctrl_on_a_header_adds_to_a_loose_screen(page):
    pg, errors = page
    _reset(pg)
    pg.locator(_lone_row(pg)).click()
    pg.locator(_header('g2')).click(modifiers=['Control'])
    assert _selected(pg) == ['LONE', 'SIDE-L', 'SIDE-R']
    assert not errors, errors


def test_shift_on_a_group_header_ranges_from_the_anchor(page):
    """The list reads LONE, SIDE-R, SIDE-L, WALL-R, WALL-L from the top."""
    pg, errors = page
    _reset(pg)
    pg.locator(_lone_row(pg)).click()
    pg.locator(_header('g2')).click(modifiers=['Shift'])
    assert _selected(pg) == ['LONE', 'SIDE-L', 'SIDE-R']
    # the anchor holds, as a second Shift on the screen rows does
    pg.locator(_header('g1')).click(modifiers=['Shift'])
    assert _selected(pg) == ['LONE', 'SIDE-L', 'SIDE-R', 'WALL-L', 'WALL-R']
    pg.locator(_header('g2')).click(modifiers=['Shift'])
    assert _selected(pg) == ['LONE', 'SIDE-L', 'SIDE-R']
    assert not errors, errors


def test_shift_from_header_to_header_takes_both_whole_either_way(page):
    pg, errors = page
    _reset(pg)
    pg.locator(_header('g1')).click()
    pg.locator(_header('g2')).click(modifiers=['Shift'])
    assert _selected(pg) == ['SIDE-L', 'SIDE-R', 'WALL-L', 'WALL-R']
    pg.locator(_header('g2')).click()
    pg.locator(_header('g1')).click(modifiers=['Shift'])
    assert _selected(pg) == ['SIDE-L', 'SIDE-R', 'WALL-L', 'WALL-R']
    assert not errors, errors


def test_shift_on_a_header_after_a_ctrl_ranges_like_the_rows(page):
    """Ctrl leaves the anchor on the first click, as on the screen rows."""
    pg, errors = page
    _reset(pg)
    pg.locator(_lone_row(pg)).click()
    pg.locator(_header('g1')).click(modifiers=['Control'])
    assert _selected(pg) == ['LONE', 'WALL-L', 'WALL-R']
    pg.locator(_header('g2')).click(modifiers=['Shift'])
    assert _selected(pg) == ['LONE', 'SIDE-L', 'SIDE-R']
    assert not errors, errors


def test_the_read_only_group_name_takes_ctrl_and_shift_but_a_plain_click_stays_the_fields(page):
    pg, errors = page
    _reset(pg)
    name = lambda g: f'#layers-list .screen-group[data-group-id="{g}"] .screen-group-name-input'
    pg.locator(_header('g1')).click()
    pg.locator(name('g2')).click(modifiers=['Control'])
    assert _selected(pg) == ['SIDE-L', 'SIDE-R', 'WALL-L', 'WALL-R']
    pg.locator(_header('g1')).click()
    pg.locator(name('g2')).click(modifiers=['Shift'])
    assert _selected(pg) == ['SIDE-L', 'SIDE-R', 'WALL-L', 'WALL-R']
    pg.locator(_header('g1')).click()
    pg.locator(name('g2')).click()
    pg.wait_for_timeout(100)
    assert _selected(pg) == ['WALL-L', 'WALL-R']
    assert pg.evaluate("(s) => document.querySelector(s).readOnly", name('g2')) is True
    pg.evaluate("() => document.activeElement && document.activeElement.blur()")
    assert not errors, errors


def test_an_open_group_name_keeps_a_ctrl_click_to_itself(page):
    pg, errors = page
    _reset(pg)
    name = '#layers-list .screen-group[data-group-id="g2"] .screen-group-name-input'
    pg.locator(_header('g1')).click()
    pg.locator(name).dblclick()
    settled(pg, lambda: pg.evaluate("(s) => document.querySelector(s).readOnly", name), lambda v: v is False)
    pg.locator(name).click(modifiers=['Control'])
    assert _selected(pg) == ['WALL-L', 'WALL-R']
    assert pg.evaluate("(s) => document.querySelector(s).readOnly", name) is False
    pg.keyboard.press('Escape')
    assert not errors, errors


def test_undo_puts_each_groups_values_back(page):
    pg, errors = page
    _reset(pg)
    _set_wall_group_side_screens(pg)
    out = pg.evaluate("""async () => {
        const h = window.__npg, app = window.app;
        const seen = [];
        const settle = () => new Promise(r => setTimeout(r, 400));
        app.undo(); await settle();
        seen.push({ wall: h.values('g1')['pixel-map'], side: h.values('g2')['pixel-map'] });
        app.undo(); await settle();
        seen.push({ wall: h.values('g1')['pixel-map'], side: h.values('g2')['pixel-map'] });
        app.undo(); await settle();
        seen.push({ wall: h.values('g1')['pixel-map'], side: h.values('g2')['pixel-map'] });
        app.redo(); await settle();
        seen.push({ wall: h.values('g1')['pixel-map'], side: h.values('g2')['pixel-map'] });
        return seen;
    }""")
    assert out == [{'wall': 'group', 'side': 'both'},
                   {'wall': 'both', 'side': 'both'},
                   {'wall': 'group', 'side': 'group'},
                   {'wall': 'both', 'side': 'both'}], out
    assert not errors, errors


def test_the_switch_hides_with_no_group_selected(page):
    pg, errors = page
    _reset(pg)
    out = pg.evaluate("""() => {
        const h = window.__npg, app = window.app;
        h.select(['LONE']);
        const lone = h.rows();
        // a click on the hidden row changes nothing and records nothing
        const index = app.historyIndex;
        h.click('pixel-map', 'screens');
        const after = { steps: app.historyIndex - index, wall: h.values('g1'), side: h.values('g2') };
        h.select(['WALL-L']);
        const member = h.rows();
        // a group selected with an ungrouped screen still sets the group
        h.select(['LONE', 'SIDE-R']);
        const withLone = h.rows();
        return { lone, after, member, withLone };
    }""")
    for v in VIEWS:
        assert out['lone'][v]['shown'] is False, (v, out['lone'])
        assert out['member'][v]['shown'] is True, (v, out['member'])
        assert out['withLone'][v]['shown'] is True, (v, out['withLone'])
    assert out['after'] == {'steps': 0, 'wall': {v: 'group' for v in VIEWS},
                            'side': {v: 'group' for v in VIEWS}}, out
    assert not errors, errors


def test_an_old_show_opens_with_every_group_on_the_tab_value(page):
    """Client side, the open's own pass (migrateGroupNameDisplay): only
    groupNameDisplayByView, then only groupNameDisplay. Nothing visible
    changes: the canvas draws the same before and after, and a second
    pass writes nothing."""
    pg, errors = page
    _reset(pg)
    out = pg.evaluate("""() => {
        const h = window.__npg, app = window.app, p = app.project;
        const res = {};
        // only the per-tab field
        p.groupNameDisplayByView = { 'pixel-map': 'screens', power: 'both' };
        const before1 = h.drawn('pixel-map');
        res.first = app.migrateGroupNameDisplay();
        res.byView = { wall: { ...h.G('g1').nameDisplayByView }, side: { ...h.G('g2').nameDisplayByView } };
        res.byViewField = { ...p.groupNameDisplayByView };
        res.second = app.migrateGroupNameDisplay();
        res.sameDrawing1 = JSON.stringify(before1) === JSON.stringify(h.drawn('pixel-map'));
        // only the single field
        for (const g of p.groups) delete g.nameDisplayByView;
        delete p.groupNameDisplayByView;
        p.groupNameDisplay = 'both';
        const before2 = h.drawn('pixel-map');
        res.third = app.migrateGroupNameDisplay();
        res.single = { wall: { ...h.G('g1').nameDisplayByView }, side: { ...h.G('g2').nameDisplayByView } };
        res.singleField = [p.groupNameDisplay, { ...p.groupNameDisplayByView }];
        res.fourth = app.migrateGroupNameDisplay();
        res.sameDrawing2 = JSON.stringify(before2) === JSON.stringify(h.drawn('pixel-map'));
        return res;
    }""")
    want = {'pixel-map': 'screens', 'cabinet-id': 'group', 'data-flow': 'group',
            'power': 'both', 'show-look': 'group'}
    assert out['first'] is True and out['second'] is False, out
    assert out['byView'] == {'wall': want, 'side': want}, out
    assert out['byViewField'] == {'pixel-map': 'screens', 'power': 'both'}, out
    assert out['sameDrawing1'] is True, out
    all_both = {v: 'both' for v in VIEWS}
    assert out['third'] is True and out['fourth'] is False, out
    assert out['single'] == {'wall': all_both, 'side': all_both}, out
    assert out['singleField'] == ['both', all_both], out
    assert out['sameDrawing2'] is True, out
    assert not errors, errors


def test_an_old_show_file_opens_on_the_server_the_same_way(page):
    """The file open's PUT: the server gives every group each tab's value."""
    pg, errors = page
    _reset(pg)
    out = pg.evaluate("""async () => {
        const app = window.app;
        const file = JSON.parse(JSON.stringify(app.project));
        for (const g of file.groups) delete g.nameDisplayByView;
        delete file.groupNameDisplayByView;
        file.groupNameDisplay = 'screens';
        const res = await fetch('/api/project', { method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(file) });
        const back = await res.json();
        return back.groups.map(g => g.nameDisplayByView);
    }""")
    assert out == [{v: 'screens' for v in VIEWS}] * 2, out
    # the client follows the server's copy when it reloads
    pg.evaluate("() => { window.app.loadProject(); }")
    pg.wait_for_function("() => window.app.project && (window.app.project.groups || []).length === 2"
                         " && window.app.project.groups.every(g => g.nameDisplayByView)")
    vals = pg.evaluate("() => window.app.project.groups.map(g => window.app.groupNameDisplayFor('pixel-map', g))")
    assert vals == ['screens', 'screens'], vals
    # put the module's show back to no show-wide value
    pg.evaluate("""async () => {
        const app = window.app;
        for (const g of app.project.groups) delete g.nameDisplayByView;
        delete app.project.groupNameDisplay; delete app.project.groupNameDisplayByView;
        await fetch('/api/project', { method: 'PUT', headers: {'Content-Type': 'application/json'},
                                      body: JSON.stringify(app.project) });
    }""")
    pg.wait_for_timeout(300)
    pg.evaluate(HELPERS_JS)
    assert not errors, errors


def test_save_and_reopen_keeps_each_groups_values(page):
    pg, errors = page
    _reset(pg)
    _set_wall_group_side_screens(pg)
    out = pg.evaluate("""async () => {
        const app = window.app, h = window.__npg;
        await new Promise(r => setTimeout(r, 400));   // the switch's own save
        const saved = await fetch('/api/project').then(r => r.json());
        const file = JSON.parse(app.serializeProjectForFile(JSON.parse(JSON.stringify(app.project))));
        // reopen: the file's PUT, as a file open sends it
        const back = await fetch('/api/project', { method: 'PUT',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(file) }).then(r => r.json());
        const own = (p, id) => (p.groups.find(g => g.id === id) || {}).nameDisplayByView || null;
        return { saved: [own(saved, 'g1'), own(saved, 'g2')],
                 file: [own(file, 'g1'), own(file, 'g2')],
                 back: [own(back, 'g1'), own(back, 'g2')] };
    }""")
    wall = {v: 'group' for v in VIEWS}
    side = {**wall, 'pixel-map': 'screens'}
    assert out['saved'] == [wall, side], out
    assert out['file'] == [wall, side], out
    assert out['back'] == [wall, side], out
    assert not errors, errors


def test_a_duplicated_group_copies_its_values(page):
    pg, errors = page
    _reset(pg)
    _set_wall_group_side_screens(pg)
    out = pg.evaluate("""async () => {
        const app = window.app, h = window.__npg;
        const before = app.project.groups.map(g => g.id);
        const id = await app.duplicateGroup('g2');
        const copy = app.resolveGroup(id);
        const res = { made: !!copy && !before.includes(id),
                      values: copy ? h.values(id) : null,
                      own: copy ? { ...copy.nameDisplayByView } : null };
        // a copy, not the same object
        if (copy) copy.nameDisplayByView['power'] = 'both';
        res.sourcePower = h.values('g2').power;
        app.undo();
        await new Promise(r => setTimeout(r, 500));
        res.groupsAfterUndo = app.project.groups.map(g => g.id);
        return res;
    }""")
    side = {v: 'group' for v in VIEWS}
    side['pixel-map'] = 'screens'
    assert out['made'] is True, out
    assert out['values'] == side and out['own'] == side, out
    assert out['sourcePower'] == 'group', out
    assert out['groupsAfterUndo'] == ['g1', 'g2'], out
    pg.evaluate(HELPERS_JS)
    assert not errors, errors


def test_the_binder_follows_each_groups_data_and_power(page):
    """WALL on Group for Data and Screens for Power; SIDE the other way
    round. WALL prints one Data sheet and a Power sheet per member, SIDE a
    Data sheet per member and one Power sheet."""
    pg, errors = page
    _reset(pg)
    titles = pg.evaluate("""([opts]) => {
        const h = window.__npg, app = window.app;
        h.select(['WALL-L']);
        h.click('data-flow', 'group');      // already Group: no change
        h.click('power', 'screens');
        h.select(['SIDE-R']);
        h.click('data-flow', 'screens');
        const plan = app.planBinder(opts);
        return plan.filter(p => p.kind === 'power' || p.kind === 'data').map(p => p.title);
    }""", [OPTS])
    assert sorted(titles) == sorted([
        'WALL-L - Power - Front View', 'WALL-R - Power - Front View', 'WALL - Data - Front View',
        'SIDE - Power - Front View', 'SIDE-L - Data - Front View', 'SIDE-R - Data - Front View',
        'LONE - Power - Front View', 'LONE - Data - Front View']), titles
    # a sheet drawing a group or one member leaves every group's values alone
    out = pg.evaluate("""([opts]) => {
        const h = window.__npg, app = window.app;
        const plan = app.planBinder(opts);
        const i = plan.findIndex(p => p.title === 'SIDE-L - Data - Front View');
        const k = plan.findIndex(p => p.title === 'WALL - Data - Front View');
        app.renderBinderPage(opts, i);
        app.renderBinderPage(opts, k);
        return { wall: h.values('g1'), side: h.values('g2'), force: app._nameDisplayForce || null };
    }""", [OPTS])
    assert out['wall'] == {**{v: 'group' for v in VIEWS}, 'power': 'screens'}, out
    assert out['side'] == {**{v: 'group' for v in VIEWS}, 'data-flow': 'screens'}, out
    assert out['force'] is None, out
    assert not errors, errors
