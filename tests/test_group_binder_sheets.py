"""A grouped wall in the binder, and the Names switch per tab.

The owner's rulings of 2026-10-01, on a show whose group USC (USC SR + USC
SL) is routed as one screen: "when i print a grouped screen it doesnt
include USC SL in the binder. this is bad and needs fixing". A wall routed
as one keeps every port and circuit on its first member, and the set made
a sheet per member with something of its own - so the other member never
printed.

  * The NAMES switch is per tab ("Yes, per tab"): Pixel Map, Cabinet ID,
    Data, Power and Show Look keep their own value; an old show's single
    project.groupNameDisplay starts every tab on it.
  * The binder follows the Power and Data tabs' values, side by side ("say
    power is set to label by group name then power will be by group and if
    data is set to screens then it will be 2 different"):
      Group    ONE sheet for the group on that side, titled by the group,
               its map every member, rulers straight through, the group's
               figures;
      Screens  a sheet per member - every member, carrying anything of its
               own or not - its map that member alone, a port or circuit
               crossing members listed on each it touches ("also on ...");
      Both     asked per group at export ("if set to both then ask per
               group"), the answer saved with project.binder.
  * A group whose members each route alone keeps its per-member sheets.
  * An ungrouped show prints as before.

Run locally:
    python3 -m pytest tests/test_group_binder_sheets.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Two 4 x 3 walls of 200 px cabinets side by side, the same panel, the same
# wattage and the same flow, grouped as WALL: the group routes as ONE wall on
# both sides - WALL-L carries every port and circuit - and a data port runs a
# whole row across both members. LONE is an ungrouped screen beside them.
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
    await add({name: 'LONE', columns: 3, rows: 2, cabinet_width: 128, cabinet_height: 128,
               powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
               powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor', offset_x: 2000});
    let p = await j('GET', '/api/project');
    const L = p.layers.find(l => l.name === 'WALL-L');
    const R = p.layers.find(l => l.name === 'WALL-R');
    L.group_id = 'g1'; R.group_id = 'g1';
    p.groups = [{id: 'g1', name: 'WALL', layer_ids: [L.id, R.id]}];
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('group_binder_setup');
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Group Binder Seed');
    const l = app.project.layers.find(x => x.name === 'WALL-L');
    const r = app.project.layers.find(x => x.name === 'WALL-R');
    const lone = app.project.layers.find(x => x.name === 'LONE');
    return { l: l.id, r: r.id, lone: lone.id,
             dataPeer: app.isServedByPeerRouting(r, 'data'),
             powerPeer: app.isServedByPeerRouting(r, 'power'),
             crossing: app._pullPortRuns(l).some(run => run.layers.some(x => x && x.id === r.id)
                                                     && run.layers.some(x => x && x.id === l.id)) };
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
        'scope': {'kind': 'show'}, 'cover': False, 'pull': True, 'hardware': False,
        'wiring': False, 'titleBlock': True}


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
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(600)
    # the fixture's premise: one wall on both sides, a port across members
    assert ids['dataPeer'] is True and ids['powerPeer'] is True, ids
    assert ids['crossing'] is True, ids
    yield pg, ids, errors
    context.close()


# One plan, and the named sheets rendered, under a per-tab Names setting
# (`names`, merged onto groupNameDisplayByView) and an optional setup body
# run against (app, L, R) that may return an undo fn - all put back after.
RUN_JS = """([ids, opts, names, setupSrc, titles]) => {
    const app = window.app;
    const byId = (id) => app.project.layers.find(l => l.id === id);
    const L = byId(ids.l), R = byId(ids.r);
    const had = Object.prototype.hasOwnProperty.call(app.project, 'groupNameDisplayByView');
    const was = app.project.groupNameDisplayByView;
    const binder = app.project.binder;
    if (names) app.project.groupNameDisplayByView = { ...(was || {}), ...names };
    const setup = setupSrc ? new Function('app', 'L', 'R', setupSrc) : null;
    const undo = setup ? setup(app, L, R) : null;
    try {
        const plan = app.planBinder(opts);
        const out = { plan: plan.map(p => ({ title: p.title, sheetTitle: p.sheetTitle, kind: p.kind,
                                              layerId: p.layerId, groupId: p.groupId || null,
                                              layerIds: p.layerIds || null })) };
        out.sheets = {};
        for (const t of titles || []) {
            const i = plan.findIndex(p => p.title === t);
            if (i < 0) { out.sheets[t] = null; continue; }
            const r = app.renderBinderPage(opts, i);
            out.sheets[t] = { texts: r.texts, map: r.map, wiring: r.wiring,
                              ops: r.record.ops.filter(o => o.op === 'text') };
        }
        out.after = { byView: app.project.groupNameDisplayByView || null,
                      visible: app.project.layers.map(l => l.visible !== false) };
        return out;
    } finally {
        if (typeof undo === 'function') undo();
        if (had) app.project.groupNameDisplayByView = was; else delete app.project.groupNameDisplayByView;
        app.project.binder = binder;
    }
}"""


def _run(pg, ids, names=None, setup=None, titles=(), opts=None):
    return pg.evaluate(RUN_JS, [ids, opts or OPTS, names, setup, list(titles)])


def _titles(out, kinds=('power', 'data', 'wiring')):
    return [p['title'] for p in out['plan'] if p['kind'] in kinds]


GROUP = {'power': 'group', 'data-flow': 'group'}
SCREENS = {'power': 'screens', 'data-flow': 'screens'}


def _ruler_numbers(sheet):
    """The column ruler's numbers: the bold digits over the wall."""
    m = sheet['map']
    return sorted(int(o['text']) for o in sheet['ops']
                  if o['text'].isdigit() and m['y'] - 60 < o['y'] < m['y']
                  and m['x'] - 5 <= o['x'] <= m['x'] + m['w'] + 5)


def _screens_table(texts):
    """A pull sheet's SCREENS table, its texts."""
    return texts[texts.index('SCREENS') + 1:]


def _aspect(sheet):
    m = sheet['map']
    return m['w'] / m['h']


def test_group_prints_one_sheet_per_side_drawing_every_member(page):
    """Names on Group: ONE Power and ONE Data sheet, titled by the group
    ("WALL · DATA · FRONT VIEW"), each map drawing both 4 x 3 walls - an
    8 x 3 picture - its rulers numbering 1 to 8 straight through, its
    FACTS the group's."""
    pg, ids, errors = page
    out = _run(pg, ids, GROUP, titles=['WALL - Data - Front View', 'WALL - Power - Front View'])
    assert _titles(out) == ['WALL - Power - Front View', 'WALL - Data - Front View',
                            'LONE - Power - Front View', 'LONE - Data - Front View'], _titles(out)
    sheet = next(p for p in out['plan'] if p['title'] == 'WALL - Data - Front View')
    assert sheet['sheetTitle'] == 'WALL · DATA · FRONT VIEW'
    assert sheet['groupId'] == 'g1' and sorted(sheet['layerIds']) == sorted([ids['l'], ids['r']]), sheet
    data = out['sheets']['WALL - Data - Front View']
    assert _aspect(data) == pytest.approx(8 / 3, rel=0.02), data['map']
    assert _ruler_numbers(data) == [1, 5, 8], _ruler_numbers(data)
    texts = data['texts']
    assert 'Screen' in texts and texts[texts.index('Screen') + 1].startswith('4 × 3 + 4 × 3 · 24 panels'), texts
    assert not any('also on' in t for t in texts), texts
    power = out['sheets']['WALL - Power - Front View']
    assert _aspect(power) == pytest.approx(8 / 3, rel=0.02), power['map']
    # every screen is put back as it was, and the tab's own value
    assert all(out['after']['visible']), out['after']
    assert not errors, errors


def test_screens_prints_every_member_with_its_own_wall(page):
    """Names on Screens: WALL-L and WALL-R each get a Power and a Data sheet
    - WALL-R too, which carries nothing of its own (the bug) - each map
    drawing that member's 4 x 3 alone, and the port running across both
    walls is listed on each, saying where the rest of it is."""
    pg, ids, errors = page
    titles = ['WALL-L - Data - Front View', 'WALL-R - Data - Front View', 'WALL-R - Power - Front View']
    out = _run(pg, ids, SCREENS, titles=titles)
    assert _titles(out) == ['WALL-L - Power - Front View', 'WALL-L - Data - Front View',
                            'WALL-R - Power - Front View', 'WALL-R - Data - Front View',
                            'LONE - Power - Front View', 'LONE - Data - Front View'], _titles(out)
    for t in titles:
        assert _aspect(out['sheets'][t]) == pytest.approx(4 / 3, rel=0.02), (t, out['sheets'][t]['map'])
    l_texts = out['sheets']['WALL-L - Data - Front View']['texts']
    r_texts = out['sheets']['WALL-R - Data - Front View']['texts']
    assert any('also on WALL-R' in t for t in l_texts), l_texts
    assert any('also on WALL-L' in t for t in r_texts), r_texts
    # rulers from 1 per screen: a 4-column wall numbers 1 to 4, never 8
    assert _ruler_numbers(out['sheets']['WALL-R - Data - Front View']) == [1, 4], \
        _ruler_numbers(out['sheets']['WALL-R - Data - Front View'])
    # WALL-R's own Ports count is the ports on its cabinets
    assert r_texts[r_texts.index('Ports') + 1].endswith('ports') or r_texts[r_texts.index('Ports') + 1].endswith('port')
    sheet = next(p for p in out['plan'] if p['title'] == 'WALL-R - Data - Front View')
    assert sheet['layerId'] == ids['r'] and sheet['groupId'] == 'g1', sheet
    assert not errors, errors


def test_mixed_sides_power_by_group_data_by_screens(page):
    """Power on Group, Data on Screens: one WALL Power sheet, then a Data
    sheet per member ("if data is set to screens then it will be 2
    different")."""
    pg, ids, errors = page
    out = _run(pg, ids, {'power': 'group', 'data-flow': 'screens'})
    assert _titles(out) == ['WALL - Power - Front View', 'WALL-L - Data - Front View',
                            'WALL-R - Data - Front View',
                            'LONE - Power - Front View', 'LONE - Data - Front View'], _titles(out)
    out = _run(pg, ids, {'power': 'screens', 'data-flow': 'group'})
    assert _titles(out) == ['WALL-L - Power - Front View', 'WALL-R - Power - Front View',
                            'WALL - Data - Front View',
                            'LONE - Power - Front View', 'LONE - Data - Front View'], _titles(out)
    assert not errors, errors


def test_wiring_follows_the_same_choice(page):
    """The wiring sheet on a side does the same: one WALL Data Wiring sheet
    on Group, one per member on Screens - each rendered without error."""
    pg, ids, errors = page
    opts = dict(OPTS, wiring=True)
    out = _run(pg, ids, GROUP, opts=opts, titles=['WALL - Data Wiring', 'WALL - Power Wiring'])
    assert 'WALL - Data Wiring' in _titles(out) and 'WALL - Power Wiring' in _titles(out), _titles(out)
    assert not any(t.startswith('WALL-') for t in _titles(out)), _titles(out)
    assert out['sheets']['WALL - Data Wiring'] and out['sheets']['WALL - Power Wiring']
    out = _run(pg, ids, SCREENS, opts=opts, titles=['WALL-R - Data Wiring', 'WALL-R - Power Wiring'])
    for t in ('WALL-L - Data Wiring', 'WALL-R - Data Wiring', 'WALL-L - Power Wiring', 'WALL-R - Power Wiring'):
        assert t in _titles(out), _titles(out)
    assert out['sheets']['WALL-R - Data Wiring'] and out['sheets']['WALL-R - Power Wiring']
    assert not errors, errors


def test_a_group_not_routed_as_one_keeps_its_member_sheets(page):
    """"Route data as one screen" off: each member carries its own ports, so
    the Data side prints a sheet per member with ports of its own whatever
    the Data tab says; Power, still routed as one, follows its tab."""
    pg, ids, errors = page
    setup = """
        const g = app.project.groups[0];
        const was = g.routeDataAsOne;
        g.routeDataAsOne = false;
        return () => { if (was === undefined) delete g.routeDataAsOne; else g.routeDataAsOne = was; };
    """
    out = _run(pg, ids, GROUP, setup)
    assert _titles(out) == ['WALL - Power - Front View', 'WALL-L - Data - Front View',
                            'WALL-R - Data - Front View',
                            'LONE - Power - Front View', 'LONE - Data - Front View'], _titles(out)
    assert not errors, errors


def test_an_ungrouped_show_prints_as_before(page):
    """No group: a sheet per screen, as before, no group fields on the plan."""
    pg, ids, errors = page
    setup = """
        const g = app.project.groups; const gl = L.group_id, gr = R.group_id;
        app.project.groups = []; delete L.group_id; delete R.group_id;
        return () => { app.project.groups = g; L.group_id = gl; R.group_id = gr; };
    """
    out = _run(pg, ids, GROUP, setup)
    # the loose screens run alphabetically, as they always have
    assert _titles(out) == ['LONE - Power - Front View', 'LONE - Data - Front View',
                            'WALL-L - Power - Front View', 'WALL-L - Data - Front View',
                            'WALL-R - Power - Front View', 'WALL-R - Data - Front View'], _titles(out)
    assert all(p['groupId'] is None for p in out['plan']), out['plan']
    assert not errors, errors


def test_both_asks_at_export_and_remembers_the_answer(page):
    """Data on Both: the export dialog shows a Groups row "WALL  Data:
    [Group] [Screens]", Group until answered; picking Screens is saved with
    project.binder, read back through readBinderOptions, and the plan
    prints the Data side by screens. Power on Group asks nothing."""
    pg, ids, errors = page
    out = pg.evaluate("""async () => {
        const app = window.app;
        const was = app.project.groupNameDisplayByView;
        const binder = app.project.binder;
        app.project.groupNameDisplayByView = { ...(was || {}), power: 'group', 'data-flow': 'both' };
        try {
            app.openExportModal('binder');
            await new Promise(r => setTimeout(r, 300));
            const row = document.getElementById('export-binder-groups-row');
            const before = { shown: row && row.style.display !== 'none', text: row ? row.innerText : '',
                             active: [...document.querySelectorAll('#export-binder-groups .binder-group-btn.active')]
                                 .map(b => b.dataset.side + ':' + b.dataset.mode),
                             plan: app.planBinder(app.readBinderOptions()).map(p => p.title) };
            document.querySelector('#export-binder-groups .binder-group-btn[data-side="data"][data-mode="screens"]').click();
            await new Promise(r => setTimeout(r, 200));
            const opts = app.readBinderOptions();
            const after = { saved: JSON.parse(JSON.stringify((app.project.binder || {}).groupSheets || null)),
                            asked: opts.groupSheets,
                            active: [...document.querySelectorAll('#export-binder-groups .binder-group-btn.active')]
                                 .map(b => b.dataset.side + ':' + b.dataset.mode),
                            plan: app.planBinder(opts).map(p => p.title),
                            // a caller passing its own answer overrides the saved one
                            override: app.planBinder({ ...opts, groupSheets: { g1: { data: 'group' } } }).map(p => p.title),
                            undo: app.history[app.historyIndex].action };
            return { before, after };
        } finally {
            const modal = document.getElementById('export-modal');
            if (modal) modal.style.display = 'none';
            app.project.groupNameDisplayByView = was;
            app.project.binder = binder;
        }
    }""")
    b, a = out['before'], out['after']
    assert b['shown'] and 'WALL' in b['text'] and 'Data:' in b['text'] and 'Power:' not in b['text'], b
    assert b['active'] == ['data:group'], b
    assert 'WALL - Data - Front View' in b['plan'], b['plan']
    assert a['saved'] == {'g1': {'data': 'screens'}} and a['asked'] == {'g1': {'data': 'screens'}}, a
    assert a['active'] == ['data:screens'], a
    assert 'WALL-L - Data - Front View' in a['plan'] and 'WALL-R - Data - Front View' in a['plan'], a['plan']
    assert 'WALL - Power - Front View' in a['plan'], a['plan']
    assert 'WALL - Data - Front View' in a['override'], a['override']
    assert a['undo'] == 'Set Group Sheets', a
    assert not errors, errors


def test_names_switch_is_per_tab(page):
    """Each tab keeps its own Names value: a click on the Power tab's switch
    changes Power alone, as one history entry; an old show's single
    groupNameDisplay starts every tab on it; the canvas labels each view by
    its own tab's value."""
    pg, ids, errors = page
    out = pg.evaluate("""async () => {
        const app = window.app;
        const had = Object.prototype.hasOwnProperty.call(app.project, 'groupNameDisplayByView');
        const was = app.project.groupNameDisplayByView, old = app.project.groupNameDisplay;
        const r = window.canvasRenderer, view = r.viewMode;
        try {
            delete app.project.groupNameDisplayByView;
            app.project.groupNameDisplay = 'both';
            const VIEWS = ['pixel-map', 'cabinet-id', 'data-flow', 'power', 'show-look'];
            const migrated = VIEWS.map(v => app.groupNameDisplayFor(v));
            const steps = app.historyIndex;
            document.querySelector('.name-display-btn[data-name-view="power"][data-name-display="screens"]').click();
            const after = VIEWS.map(v => app.groupNameDisplayFor(v));
            const stored = { ...app.project.groupNameDisplayByView };
            const entry = { steps: app.historyIndex - steps, action: app.history[app.historyIndex].action };
            const active = [...document.querySelectorAll('.name-display-btn.active')]
                .map(b => b.dataset.nameView + ':' + b.dataset.nameDisplay).sort();
            const modes = {};
            for (const v of VIEWS) { r.viewMode = v; modes[v] = r._groupNameMode(); }
            return { migrated, after, stored, entry, active, modes };
        } finally {
            r.viewMode = view;
            if (had) app.project.groupNameDisplayByView = was; else delete app.project.groupNameDisplayByView;
            if (old === undefined) delete app.project.groupNameDisplay; else app.project.groupNameDisplay = old;
            app.refreshNameDisplayButtons();
        }
    }""")
    assert out['migrated'] == ['both'] * 5, out
    assert out['after'] == ['both', 'both', 'both', 'screens', 'both'], out
    assert out['stored'] == {'pixel-map': 'both', 'cabinet-id': 'both', 'data-flow': 'both',
                             'power': 'screens', 'show-look': 'both'}, out
    assert out['entry'] == {'steps': 1, 'action': 'Change Name Display'}, out
    assert out['active'] == ['cabinet-id:both', 'data-flow:both', 'pixel-map:both',
                             'power:screens', 'show-look:both'], out
    assert out['modes'] == {'pixel-map': 'both', 'cabinet-id': 'both', 'data-flow': 'both',
                            'power': 'screens', 'show-look': 'both'}, out
    assert not errors, errors


def test_pull_sheet_names_the_group_it_prints(page):
    """The pull sheet's Screens table names what the set prints: on Group
    both sides, one WALL row with both walls' figures; on Screens, a row
    per member."""
    pg, ids, errors = page
    out = _run(pg, ids, GROUP, titles=['Pull - WALL, LONE'])
    pull = [p['title'] for p in out['plan'] if p['kind'] == 'pull']
    assert pull, out['plan']
    out = _run(pg, ids, GROUP, titles=pull)
    # (the cable rows' labels above it name the screens their jumpers are
    # on, as the pull list says; the SCREENS table is the set's own)
    texts = _screens_table(out['sheets'][pull[0]]['texts'])
    assert 'WALL' in texts and '4 × 3 + 4 × 3' in texts, texts
    assert 'WALL-L' not in texts and 'WALL-R' not in texts, texts
    out = _run(pg, ids, SCREENS, titles=pull)
    texts = _screens_table(out['sheets'][pull[0]]['texts'])
    assert 'WALL-L' in texts and 'WALL-R' in texts and 'WALL' not in texts, texts
    assert not errors, errors


# ── Follow-ups, the owner's answers of 2026-10-01 ─────────────────────────

def _cables(texts):
    """A screen sheet's CABLES THIS SCREEN cells, up to its FACTS."""
    i = texts.index('CABLES THIS SCREEN')
    return texts[i + 1:texts.index('FACTS', i)]


def test_a_members_cables_are_its_own_and_a_split_one_is_on_both(page):
    """"separate them. if the data or power splits then mention it on both.
    pull sheets only account for one though not double": on Screens each
    member's CABLES THIS SCREEN lists the cables landing on its own
    cabinets - WALL-R's no longer an empty table or a pointer to WALL-L -
    and a jumper joining the two walls is listed on both, marked "also on"
    the other; the pull list still counts every jumper once."""
    pg, ids, errors = page
    titles = ['WALL-L - Data - Front View', 'WALL-R - Data - Front View',
              'WALL-L - Power - Front View', 'WALL-R - Power - Front View']
    out = _run(pg, ids, SCREENS, titles=titles)
    for t in titles:
        cells = _cables(out['sheets'][t]['texts'])
        assert 'no cables typed' not in cells and not any(c.startswith('listed with') for c in cells), (t, cells)
    l_data = _cables(out['sheets']['WALL-L - Data - Front View']['texts'])
    r_data = _cables(out['sheets']['WALL-R - Data - Front View']['texts'])
    assert 'Data Jump · also on WALL-R' in l_data, l_data
    assert 'Data Jump · also on WALL-L' in r_data, r_data
    assert 'Data Jump' in r_data, r_data          # its own, inside its wall
    counts = pg.evaluate("""(ids) => {
        const app = window.app;
        const list = app.buildPullSheet();
        const jumps = (rows) => rows.filter(r => r.type === 'Data Jump').reduce((a, r) => a + r.qty, 0);
        return { total: jumps(list.totals),
                 links: Object.values(list.byScreen).reduce((a, s) => a + s.jumpers.data, 0),
                 merged: Object.values(list.byScreen).reduce((a, s) => a + jumps(s.rows), 0) };
    }""", ids)
    assert counts['total'] == counts['links'] == counts['merged'] and counts['total'] > 0, counts
    assert not errors, errors


def test_a_crossing_port_lists_on_the_member_without_its_label(page):
    """"make sure it's shown on both if the label is on there": a port whose
    run starts - its label disc - on WALL-L and runs on into WALL-R is a row
    on WALL-R's Data sheet too, "<label> · also on WALL-L", with the whole
    port's PANELS; and WALL-R's Data Wiring sheet carries a stub for it."""
    pg, ids, errors = page
    port = pg.evaluate("""(ids) => {
        const app = window.app;
        const L = app.project.layers.find(l => l.id === ids.l);
        const run = app._pullPortRuns(L).find(r => r.layers[0] && r.layers[0].id === ids.l
            && r.layers.some(x => x && x.id === ids.r));
        return run ? { label: run.label, panels: run.panels.length,
                       onR: run.layers.filter(x => x && x.id === ids.r).length } : null;
    }""", ids)
    assert port and port['onR'] > 0, port
    out = _run(pg, ids, SCREENS, opts=dict(OPTS, wiring=True),
               titles=['WALL-R - Data - Front View', 'WALL-R - Data Wiring'])
    texts = out['sheets']['WALL-R - Data - Front View']['texts']
    row = '%s · also on WALL-L' % port['label']
    assert row in texts, texts
    assert texts[texts.index(row) + 3] == str(port['panels']), texts[texts.index(row):texts.index(row) + 4]
    discs = [d['text'] for h in out['sheets']['WALL-R - Data Wiring']['wiring']['halves'] for d in h['discs']]
    assert port['label'] in discs, discs
    assert not errors, errors


def test_the_pull_sheet_follows_each_side(page):
    """"Depends on if it is power or data and on if grouped or screen
    group": Power on Group with Data on Screens - the SCREENS table has one
    WALL line carrying the circuits and none of the ports, and a line per
    member carrying the ports and none of the circuits; the panels sit on
    the member lines only, so none is counted twice."""
    pg, ids, errors = page
    out = _run(pg, ids, {'power': 'group', 'data-flow': 'screens'})
    pull = [p['title'] for p in out['plan'] if p['kind'] == 'pull']
    out = _run(pg, ids, {'power': 'group', 'data-flow': 'screens'}, titles=pull)
    texts = _screens_table(out['sheets'][pull[0]]['texts'])
    i, li, ri = texts.index('WALL'), texts.index('WALL-L'), texts.index('WALL-R')
    wall, lrow, rrow = texts[i:i + 6], texts[li:li + 6], texts[ri:ri + 6]
    assert wall[1] == '—' and wall[2] == '—' and wall[3] != '—' and wall[4] == '—', wall
    assert lrow[2] == '12' and lrow[3] == '—' and lrow[4] != '—', lrow
    assert rrow[2] == '12' and rrow[3] == '—' and rrow[4] != '—', rrow
    # the other way round: one data line, a power line per member
    out = _run(pg, ids, {'power': 'screens', 'data-flow': 'group'}, titles=pull)
    texts = _screens_table(out['sheets'][pull[0]]['texts'])
    i, li = texts.index('WALL'), texts.index('WALL-L')
    assert texts[i + 3] == '—' and texts[i + 4] != '—', texts[i:i + 6]
    assert texts[li + 3] != '—' and texts[li + 4] == '—', texts[li:li + 6]
    assert not errors, errors
