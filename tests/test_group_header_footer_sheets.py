"""A grouped wall's Header/Footer sheet follows the Header/Footer tab's
Names switch, the way its Power and Data sheets follow theirs.

The owner, 2026-11-03, on a show (Boston) whose Header/Footer tab names its
group by Group: "so the header/footer tab doesn't follow those rules. does
it need an update?" - the binder printed a Header/Footer sheet per member
whatever the switch said.

  Group    ONE sheet for the group, titled by the group, its map every
           member and its bars, its bar tables every member's bars tallied
           together;
  Screens  a sheet per member with bars, as before;
  Both     asked per group at export, saved beside the Power and Data
           answers (project.binder.groupSheets[g].rigging).

Bars hang on each screen of their own, so no "routed as one" test applies:
a group whose members route alone still prints one sheet on Group.

Run locally:
    python3 -m pytest tests/test_group_header_footer_sheets.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Two 4 x 3 walls side by side grouped as WALL, each with its own header
# bars and WALL-L with footer bars too; LONE, ungrouped, has header bars of
# its own. Every screen routes on its own (no crossing), so the group is
# routed as one on neither side.
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
    // a different wattage: the walls do not match, so power never walks across them
    await add({...wall, name: 'WALL-R', offset_x: 800, panelWatts: 150});
    await add({name: 'LONE', columns: 3, rows: 2, cabinet_width: 128, cabinet_height: 128,
               powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
               powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
               processorType: 'novastar-armor', offset_x: 2000});
    let p = await j('GET', '/api/project');
    const L = p.layers.find(l => l.name === 'WALL-L');
    const R = p.layers.find(l => l.name === 'WALL-R');
    const lone = p.layers.find(l => l.name === 'LONE');
    L.group_id = 'g1'; R.group_id = 'g1';
    L.riggingBars = [2, 2]; L.riggingFooterBars = [4];
    R.riggingBars = [2, 1, 1];
    lone.riggingBars = [3];
    p.groups = [{id: 'g1', name: 'WALL', layer_ids: [L.id, R.id], routeDataAsOne: false}];
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('group_rig_setup');
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Group Header Footer Seed');
    const l = app.project.layers.find(x => x.name === 'WALL-L');
    const r = app.project.layers.find(x => x.name === 'WALL-R');
    return { l: l.id, r: r.id, lone: app.project.layers.find(x => x.name === 'LONE').id,
             bars: [l.riggingBars, r.riggingBars, l.riggingFooterBars],
             peer: app.isServedByPeerRouting(r, 'power') || app.isServedByPeerRouting(r, 'data') };
}"""

OPTS = {'sheet': 'tabloid', 'palette': 'colour', 'sides': {'power': True, 'data': True},
        'scope': {'kind': 'show'}, 'cover': False, 'pull': False, 'hardware': False,
        'wiring': False, 'rigging': True, 'titleBlock': True}


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
    assert ids['bars'] == [[2, 2], [2, 1, 1], [4]], ids
    assert ids['peer'] is False, ids
    yield pg, ids, errors
    context.close()


# One plan under a per-tab Names setting (merged onto groupNameDisplayByView)
# and the named sheets rendered - all put back after.
RUN_JS = """([opts, names, titles, answers]) => {
    const app = window.app;
    const had = Object.prototype.hasOwnProperty.call(app.project, 'groupNameDisplayByView');
    const was = app.project.groupNameDisplayByView;
    const binder = app.project.binder;
    if (names) app.project.groupNameDisplayByView = { ...(was || {}), ...names };
    const o = answers ? { ...opts, groupSheets: answers } : opts;
    try {
        const plan = app.planBinder(o);
        const out = { plan: plan.map(p => ({ title: p.title, sheetTitle: p.sheetTitle, kind: p.kind,
                                              layerId: p.layerId, groupId: p.groupId || null,
                                              layerIds: p.layerIds || null, extent: p.extent })) };
        out.sheets = {};
        for (const t of titles || []) {
            const i = plan.findIndex(p => p.title === t);
            if (i < 0) { out.sheets[t] = null; continue; }
            const r = app.renderBinderPage(o, i);
            out.sheets[t] = { texts: r.texts, map: r.map };
        }
        out.visible = app.project.layers.map(l => l.visible !== false);
        out.byView = app.project.groupNameDisplayByView || null;
        return out;
    } finally {
        if (had) app.project.groupNameDisplayByView = was; else delete app.project.groupNameDisplayByView;
        app.project.binder = binder;
    }
}"""


def _run(pg, names=None, titles=(), opts=None, answers=None):
    return pg.evaluate(RUN_JS, [opts or OPTS, names, list(titles), answers])


def _titles(out, kinds=('power', 'data', 'rigging')):
    return [p['title'] for p in out['plan'] if p['kind'] in kinds]


def _rig(out):
    return _titles(out, ('rigging',))


def _qty_after(texts, label):
    """The qty cell of the first table row whose first cell is `label`."""
    i = texts.index(label)
    return texts[i + 1:i + 3]


def test_group_prints_one_header_footer_sheet_for_the_wall(page):
    """Header/Footer on Group: ONE "WALL - Header/Footer" sheet carrying the
    group and both members, its map both walls (an 8 x 3 picture), its
    Header bars table every member's header bars together - 2 + 2 on
    WALL-L and 2 + 1 + 1 on WALL-R: three doubles, two singles, 5 in all -
    and its Footer bars WALL-L's one 4-way. LONE keeps its own sheet."""
    pg, ids, errors = page
    out = _run(pg, {'rigging': 'group'}, titles=['WALL - Header/Footer - Front View'])
    assert _rig(out) == ['WALL - Header/Footer - Front View', 'LONE - Header/Footer - Front View'], _rig(out)
    sheet = next(p for p in out['plan'] if p['title'] == 'WALL - Header/Footer - Front View')
    assert sheet['sheetTitle'] == 'WALL · HEADER/FOOTER · FRONT VIEW', sheet
    assert sheet['groupId'] == 'g1' and sorted(sheet['layerIds']) == sorted([ids['l'], ids['r']]), sheet
    drawn = out['sheets']['WALL - Header/Footer - Front View']
    m = drawn['map']
    assert m and m['w'] / m['h'] == pytest.approx(8 / 3, rel=0.02), m
    texts = drawn['texts']
    assert 'HEADER BARS' in texts and 'FOOTER BARS' in texts, texts
    header = texts[texts.index('HEADER BARS'):texts.index('FOOTER BARS')]
    footer = texts[texts.index('FOOTER BARS'):]
    assert _qty_after(header, 'Header Bar - Double') == ['2', '3'], header
    assert _qty_after(header, 'Header Bar - Single') == ['1', '2'], header
    assert header[header.index('Total') + 2] == '5', header
    assert _qty_after(footer, 'Footer Bar - 4-way') == ['4', '1'], footer
    assert footer[footer.index('Total') + 2] == '1', footer
    assert all(out['visible']), out
    assert not errors, errors


def test_screens_prints_a_sheet_per_member(page):
    """Header/Footer on Screens: a sheet for each member with bars, as
    before, each its own wall."""
    pg, ids, errors = page
    out = _run(pg, {'rigging': 'screens'})
    assert _rig(out) == ['WALL-L - Header/Footer - Front View', 'WALL-R - Header/Footer - Front View',
                         'LONE - Header/Footer - Front View'], _rig(out)
    assert not errors, errors


def test_the_group_sheet_needs_no_routing_as_one(page):
    """The walls route alone - their Power and Data sheets stay one per
    member whatever the Power and Data tabs say - but the Header/Footer
    sheet is still the group's on Group, after both members' sheets."""
    pg, ids, errors = page
    out = _run(pg, {'rigging': 'group', 'power': 'group', 'data-flow': 'group'})
    t = _titles(out)
    assert 'WALL - Power - Front View' not in t and 'WALL - Data - Front View' not in t, t
    assert 'WALL - Header/Footer - Front View' in t, t
    wall = [x for x in t if x.startswith('WALL')]
    assert wall[-1] == 'WALL - Header/Footer - Front View', wall
    assert t.index('WALL - Header/Footer - Front View') < t.index('LONE - Header/Footer - Front View'), t
    assert not errors, errors


def test_the_rigging_tick_off_prints_none(page):
    pg, ids, errors = page
    out = _run(pg, {'rigging': 'group'}, opts=dict(OPTS, rigging=False))
    assert _rig(out) == [], _rig(out)
    assert not errors, errors


def test_a_group_without_bars_prints_no_header_footer_sheet(page):
    """No bar on any member: no Header/Footer sheet for the group at all."""
    pg, ids, errors = page
    out = pg.evaluate("""(opts) => {
        const app = window.app;
        const ms = app.project.layers.filter(l => l.group_id === 'g1');
        const saved = ms.map(l => [l, l.riggingBars, l.riggingFooterBars]);
        const was = app.project.groupNameDisplayByView;
        app.project.groupNameDisplayByView = { ...(was || {}), rigging: 'group' };
        try {
            ms.forEach(l => { l.riggingBars = []; l.riggingFooterBars = []; });
            return app.planBinder(opts).filter(p => p.kind === 'rigging').map(p => p.title);
        } finally {
            saved.forEach(([l, h, f]) => { l.riggingBars = h; l.riggingFooterBars = f; });
            app.project.groupNameDisplayByView = was;
        }
    }""", OPTS)
    assert out == ['LONE - Header/Footer - Front View'], out
    assert not errors, errors


def test_a_one_screen_scope_prints_the_groups_sheet(page):
    pg, ids, errors = page
    opts = dict(OPTS, scope={'kind': 'screen', 'layerId': str(ids['r'])})
    out = _run(pg, {'rigging': 'group'}, opts=opts)
    assert _rig(out) == ['WALL - Header/Footer - Front View'], _rig(out)
    out = _run(pg, {'rigging': 'screens'}, opts=opts)
    assert _rig(out) == ['WALL-R - Header/Footer - Front View'], _rig(out)
    assert not errors, errors


def test_both_asks_at_export_and_remembers_the_answer(page):
    """Header/Footer on Both: the export dialog's Groups row shows "WALL
    Header/Footer: [Group] [Screens]" - though WALL is routed as one on
    neither side, so Power and Data ask nothing - Group until answered;
    picking Screens is saved beside any Power / Data answer and the plan
    prints a sheet per member."""
    pg, ids, errors = page
    out = pg.evaluate("""async () => {
        const app = window.app;
        const was = app.project.groupNameDisplayByView;
        const binder = app.project.binder;
        app.project.groupNameDisplayByView = { ...(was || {}), power: 'both', 'data-flow': 'both', rigging: 'both' };
        const rig = (opts) => app.planBinder(opts).filter(p => p.kind === 'rigging').map(p => p.title);
        try {
            app.openExportModal('binder');
            await new Promise(r => setTimeout(r, 300));
            const row = document.getElementById('export-binder-groups-row');
            const active = () => [...document.querySelectorAll('#export-binder-groups .binder-group-btn.active')]
                .map(b => b.dataset.side + ':' + b.dataset.mode);
            const before = { shown: row && row.style.display !== 'none', text: row ? row.innerText : '',
                             active: active(), plan: rig(app.readBinderOptions()) };
            document.querySelector('#export-binder-groups .binder-group-btn[data-side="rigging"][data-mode="screens"]').click();
            await new Promise(r => setTimeout(r, 200));
            const opts = app.readBinderOptions();
            const after = { saved: JSON.parse(JSON.stringify((app.project.binder || {}).groupSheets || null)),
                            active: active(), plan: rig(opts),
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
    assert b['shown'] and 'WALL' in b['text'] and 'Header/Footer:' in b['text'], b
    assert 'Power:' not in b['text'] and 'Data:' not in b['text'], b
    assert b['active'] == ['rigging:group'], b
    assert b['plan'][0] == 'WALL - Header/Footer - Front View', b
    assert a['saved'] == {'g1': {'rigging': 'screens'}}, a
    assert a['active'] == ['rigging:screens'], a
    assert a['plan'][:2] == ['WALL-L - Header/Footer - Front View', 'WALL-R - Header/Footer - Front View'], a
    assert a['undo'] == 'Set Group Sheets', a
    assert not errors, errors


def test_a_saved_answer_survives_the_reader(page):
    """getBinderInfo keeps a 'rigging' answer and drops anything else."""
    pg, ids, errors = page
    out = pg.evaluate("""() => {
        const app = window.app;
        return app._binderGroupSheets({ g1: { rigging: 'screens', power: 'group', data: 'nope' },
                                        g2: { rigging: 'bogus' } });
    }""")
    assert out == {'g1': {'rigging': 'screens', 'power': 'group'}}, out
    assert not errors, errors
