"""A grouped wall draws and redraws its circuits as one screen.

The field report (1.6.0-beta.5): "I can't do drawings across grouped
screens." Three screens grouped as one wall, each on its own processor
canvas, all three laid out on one show canvas. The automatic circuits were
numbered per screen (S1-1 on each), so the last column of one screen could
never pair with the first column of the next, and a redraw that ran onto
the next screen found every cabinet there wired to that screen's own
circuits: refused, "already wired to circuit S1-1 on Center".

The cause: the automatic walk only crossed a group whose members share
one processor raster. That rule is about data (a port's pixel load and
the low-latency derate are measured down one raster) and was applied to
power as well. A circuit is watts on a cable; grouped screens "are one
screen when they are grouped". Power now crosses; data keeps the rule.

Each case runs on the scratch wall below and, where it applies, on one
ungrouped screen of the same columns, and the two must behave the same:
a redraw cut back across the seam, extended back across it, refused on
another circuit's cabinet, undone step by step; a custom circuit drawn
from one member into the next; a locked member still refused with its
message.

The wall: W1 (3 columns, processor canvas c2), W2 (6 columns, c1), W3
(3 columns, c3), all on show canvas c1, side by side, 4 rows of 150 W
cabinets on 208 V x 20 A, cabled top-down (tl-v), Organized, 2fers on.
Two columns draw 1,200 W, so the walk pairs columns 2 at a time.

Run locally:
    python -m pytest tests/test_group_power_draw.py -v --browser chromium
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


FETCH_COUNT_JS = """(() => {
    const real = window.fetch;
    let out = 0;
    Object.defineProperty(window, '__lrdFetchesOut', { get: () => out });
    window.fetch = function (...args) {
        out++;
        const p = real.apply(this, args);
        p.then(() => { out--; }, () => { out--; });
        return p;
    };
})()"""


def _settle(pg):
    """Every fetch the page made has answered and every layer save landed."""
    pg.wait_for_function("() => window.__lrdFetchesOut === 0")
    pg.evaluate("async () => { await window.app._layerSavesSettled(); }")
    pg.wait_for_function("() => window.__lrdFetchesOut === 0 && !window.app._saveStateTimer")


def _no_dialog(route):
    route.fulfill(status=403, content_type='application/json', body='{}')


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1440, 'height': 900})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    # A real save or open dialog would pop up on the desktop.
    for verb in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{verb}', _no_dialog)
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    _settle(pg)
    pg.evaluate(HELPERS_JS)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'power'")
    yield pg, errors
    context.close()


HELPERS_JS = r"""
window.__gw = {
    screen(o) {
        o = Object.assign({
            type: 'screen', visible: true, locked: false,
            columns: 3, rows: 4, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 150, powerVoltage: 208, powerAmperage: 20,
            processorType: 'novastar-armor', bitDepth: 8, frameRate: 60, lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-v', lastPowerFlowPattern: 'tl-v', powerCustomPath: false,
            powerOrganized: true, powerMaximize: false, powerBreakoutType: 'soca-true1',
            powerSplitters: { enabled: true, maxWays: 2, manual: { merge: [], split: [] } },
            powerCustomPaths: {}, powerCustomOverrides: [], powerCustomIndex: 1,
            group_id: null, powerSocaDistro: {}, powerSocaNumber: {},
            powerSocaLengths: {}, powerCircuitCables: {}, powerSocaKeying: 'index',
        }, o || {});
        o.panels = [];
        for (let r = 0; r < o.rows; r++) for (let c = 0; c < o.columns; c++) {
            o.panels.push({ row: r, col: c,
                x: o.offset_x + c * o.cabinet_width, y: o.offset_y + r * o.cabinet_height,
                width: o.cabinet_width, height: o.cabinet_height,
                hidden: false, blank: false, halfTile: 'none' });
        }
        return o;
    },
    canvas(id, x) {
        return { id, name: id, color: '#4A90E2', visible: true,
            raster_width: 3840, raster_height: 2160,
            show_raster_width: 3840, show_raster_height: 2160,
            workspace_x: x, workspace_y: 0, show_workspace_x: x, show_workspace_y: 0,
            data_flow_perspective: 'front', power_perspective: 'front' };
    },
    // The wall: three members on three processor canvases, one show canvas.
    wall() {
        return {
            canvases: [this.canvas('c1', 0), this.canvas('c2', 5000), this.canvas('c3', 10000)],
            active_canvas_id: 'c1',
            groups: [{ id: 'g1', name: 'Wall', layer_ids: [1, 2, 3] }],
            layers: [
                this.screen({ id: 1, name: 'W1', columns: 3, group_id: 'g1',
                    canvas_id: 'c2', show_canvas_id: 'c1', showOffsetX: 0, showOffsetY: 0 }),
                this.screen({ id: 2, name: 'W2', columns: 6, group_id: 'g1',
                    canvas_id: 'c1', showOffsetX: 384, showOffsetY: 0 }),
                this.screen({ id: 3, name: 'W3', columns: 3, group_id: 'g1',
                    canvas_id: 'c3', show_canvas_id: 'c1', showOffsetX: 1152, showOffsetY: 0 }),
            ],
        };
    },
    // One screen of the same 12 columns.
    single() {
        return {
            canvases: [this.canvas('c1', 0)],
            active_canvas_id: 'c1',
            groups: [],
            layers: [this.screen({ id: 1, name: 'W1', columns: 12, canvas_id: 'c1' })],
        };
    },
    async j(method, url, body) {
        const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body) });
        const out = await r.json();
        if (!r.ok) throw new Error(url + ': ' + JSON.stringify(out));
        return out;
    },
    async open(which) {
        const app = window.app;
        await app._layerSavesSettled();
        const project = Object.assign({ name: 'Group draw', cableUnit: 'ft' }, this[which]());
        await this.j('PUT', '/api/project', project);
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('group_power_draw');
        app.selectedLayerIds = new Set();
        app._overrideEditing = null;
        app.selectLayer(app.project.layers[0]);
        app._circuitTailCache = null;
        app._assignment = null;
        app.resetHistory('Initial State');
        app.renderLayers();
        window.canvasRenderer.fitToView();
        window.canvasRenderer.render();
        document.querySelectorAll('#app-toast-host > div').forEach(t => t.remove());
        return true;
    },
    L(n) { return window.app.project.layers.find(l => l.name === n); },
    // Every circuit of every screen, as "member:col" columns.
    circuits() {
        const app = window.app;
        app._circuitTailCache = null;
        window.canvasRenderer.render();
        const out = {};
        app.project.layers.forEach(l => {
            out[l.name] = app.screenCircuits(l).map(c => {
                const cols = [];
                c.panels.forEach((p, i) => {
                    const on = (c.layers && c.layers[i]) || l;
                    const k = `${on.name}:${p.col}`;
                    if (!cols.includes(k)) cols.push(k);
                });
                return { num: c.num, label: app.getPowerCircuitLabel(l, c.num), cols };
            });
        });
        return out;
    },
    // The screen point of a cabinet's centre, checked against the canvas's
    // own hit test so a click lands on the cabinet named.
    cell(name, col, row) {
        const app = window.app, r = window.canvasRenderer;
        const l = this.L(name);
        const p = l.panels.find(q => q.col === col && q.row === row);
        const off = app._getLayerWorkspaceOffset(l);
        const wx = off.wx + p.x + p.width / 2;
        const wy = off.wy + p.y + p.height / 2;
        const hit = r.getPanelAt(wx, wy);
        if (!hit || hit.layerId !== l.id || hit.panel !== p) {
            throw new Error(`cell ${name} ${col},${row} misses: ${JSON.stringify(hit && { l: hit.layerId, r: hit.panel.row, c: hit.panel.col })}`);
        }
        const rc = r.canvas.getBoundingClientRect();
        const sx = rc.width / r.canvas.width;
        return { x: rc.left + (r.panX + wx * r.zoom) * sx,
                 y: rc.top + (r.panY + wy * r.zoom) * sx };
    },
    // The path of circuit `num` on `owner`, as "member:col,row" steps.
    path(owner, num) {
        const app = window.app, l = this.L(owner);
        return ((l.powerCustomPaths || {})[num] || []).map(e => {
            const on = app.project.layers.find(x => x.id === app.getPathEntryLayerId(l, e));
            return `${on ? on.name : '?'}:${e.col},${e.row}`;
        });
    },
    toasts() {
        return [...document.querySelectorAll('#app-toast-host > div')]
            .map(t => t.textContent.trim()).filter(Boolean);
    },
    clearToasts() { document.querySelectorAll('#app-toast-host > div').forEach(t => t.remove()); },
};
"""


def _open(pg, which):
    pg.evaluate("(w) => window.__gw.open(w)", which)
    _settle(pg)


def _circuits(pg):
    return pg.evaluate("() => window.__gw.circuits()")


def _path(pg, owner, num):
    return pg.evaluate("([o, n]) => window.__gw.path(o, n)", [owner, num])


def _toasts(pg):
    return pg.evaluate("() => window.__gw.toasts()")


def _click(pg, name, col, row, alt=False):
    c = pg.evaluate("([n, c, r]) => window.__gw.cell(n, c, r)", [name, col, row])
    pg.mouse.move(c['x'], c['y'])
    if alt:
        pg.keyboard.down('Alt')
    pg.mouse.click(c['x'], c['y'])
    if alt:
        pg.keyboard.up('Alt')
    _settle(pg)


def _undo(pg):
    pg.evaluate("() => window.app.undo()")
    _settle(pg)


def _editing(pg):
    return pg.evaluate("() => window.app._overrideEditing")


# Where the cabinets are, per case: a wall cell is (member, col); the same
# cabinet on the single 12-column screen is ('W1', col + the member's start).
STARTS = {'W1': 0, 'W2': 3, 'W3': 9}


def _at(which, member, col):
    return (member, col) if which == 'wall' else ('W1', STARTS[member] + col)


def _flat(which, steps):
    """A path as wall columns 0..11 (member start + col), row: the same
    reading for the wall and for the single screen."""
    out = []
    for s in steps:
        on, rest = s.split(':')
        col, row = (int(v) for v in rest.split(','))
        out.append((STARTS[on] + col if which == 'wall' else col, row))
    return out


def test_a_wall_across_processor_canvases_walks_its_circuits_as_one(page):
    """The three members are numbered as one wall: the last column of W1
    pairs with W2's first as one 2fer (S1-2), W2's last with W3's first
    (S1-5), the first member numbers them all and the others report none.
    The same columns as the single 12-column screen. Data keeps its rule:
    three processor canvases are three rasters, so ports stay per member."""
    pg, errors = page
    _open(pg, 'wall')
    wall = _circuits(pg)
    assert [c['cols'] for c in wall['W1']] == [
        ['W1:0', 'W1:1'], ['W1:2', 'W2:0'], ['W2:1', 'W2:2'],
        ['W2:3', 'W2:4'], ['W2:5', 'W3:0'], ['W3:1', 'W3:2']], wall
    assert [c['label'] for c in wall['W1']] == [f'S1-{n}' for n in range(1, 7)], wall
    assert wall['W2'] == [] and wall['W3'] == [], wall
    data = pg.evaluate("""() => ['W1', 'W2', 'W3'].map(n =>
        window.app.getAutoRoutePlan(window.__gw.L(n), 'data'))""")
    assert data == [None, None, None], data
    _open(pg, 'single')
    one = _circuits(pg)['W1']
    assert [len(c['cols']) for c in one] == [len(c['cols']) for c in wall['W1']], one
    assert errors == []


@pytest.mark.parametrize('which', ['wall', 'single'])
def test_a_redraw_runs_across_the_seam_the_way_it_runs_on_one_screen(page, which):
    """Alt+click S1-2 (W1's last column and W2's first). A click on its
    first cabinet past the seam cuts it back to end there; the cabinets
    after it are held for the redraw and are drawn back across the seam
    with no refusal. A click on S1-3's cabinet is refused and named, as on
    one screen. Each step undoes on its own. Run on the wall and on one
    12-column screen, which must read the same."""
    pg, errors = page
    _open(pg, which)
    member, col = _at(which, 'W1', 2)
    _click(pg, member, col, 1, alt=True)
    assert _editing(pg)['num'] == 2
    seeded = _flat(which, _path(pg, 'W1', 2))
    assert seeded == [(2, r) for r in range(4)] + [(3, r) for r in range(4)], seeded

    # cut back across the seam: ends at W2's first cabinet
    member, col = _at(which, 'W2', 0)
    _click(pg, member, col, 0)
    assert _flat(which, _path(pg, 'W1', 2)) == seeded[:5]
    cut = [t for t in _toasts(pg) if 'now ends at' in t]
    where = 'R1C1 on W2' if which == 'wall' else 'R1C4'
    assert cut and f'now ends at {where}.' in cut[-1], _toasts(pg)

    # drawn back across the seam, onto the cabinets the redraw holds
    _click(pg, member, col, 1)
    _click(pg, member, col, 2)
    assert _flat(which, _path(pg, 'W1', 2)) == seeded[:7]
    assert not [t for t in _toasts(pg) if 'already wired' in t], _toasts(pg)

    # another circuit's cabinet is refused, named, and changes nothing
    member, col = _at(which, 'W2', 1)
    _click(pg, member, col, 0)
    refused = [t for t in _toasts(pg) if 'already wired' in t]
    where = 'R1C2 on W2' if which == 'wall' else 'R1C5'
    assert refused and refused[-1] == (
        f'Cabinet {where} is already wired to circuit S1-3. '
        'Clear it from circuit S1-3 first.'), _toasts(pg)
    assert _flat(which, _path(pg, 'W1', 2)) == seeded[:7]

    # undo, one step at a time, back to the seeded circuit
    _undo(pg)
    assert _flat(which, _path(pg, 'W1', 2)) == seeded[:6]
    _undo(pg)
    assert _flat(which, _path(pg, 'W1', 2)) == seeded[:5]
    _undo(pg)
    assert _flat(which, _path(pg, 'W1', 2)) == seeded
    assert errors == []


def test_a_custom_circuit_is_drawn_from_one_member_into_the_next(page):
    """Custom on, W1 selected: the wall is one custom screen. A circuit
    drawn down W1's last column and on into W2's first is one circuit of
    the first member, with no refusal; undo takes the steps back one by
    one, the last one across the seam first."""
    pg, errors = page
    _open(pg, 'wall')
    cb = pg.locator('#power-custom-toggle')
    cb.scroll_into_view_if_needed()
    cb.click()
    _settle(pg)
    assert pg.evaluate("() => ['W1', 'W2', 'W3'].map(n => window.app.isCustomPower(window.__gw.L(n)))") \
        == [True, True, True]
    for r in range(4):
        _click(pg, 'W1', 2, r)
    _click(pg, 'W2', 0, 3)
    _click(pg, 'W2', 0, 2)
    assert _path(pg, 'W1', 1) == ['W1:2,0', 'W1:2,1', 'W1:2,2', 'W1:2,3', 'W2:0,3', 'W2:0,2']
    assert not [t for t in _toasts(pg) if 'already wired' in t], _toasts(pg)
    # a click on an earlier cabinet, back across the seam, cuts it back
    _click(pg, 'W1', 2, 3)
    assert _path(pg, 'W1', 1) == ['W1:2,0', 'W1:2,1', 'W1:2,2', 'W1:2,3']
    _undo(pg)
    assert _path(pg, 'W1', 1)[-1] == 'W2:0,2'
    _undo(pg)
    assert _path(pg, 'W1', 1) == ['W1:2,0', 'W1:2,1', 'W1:2,2', 'W1:2,3', 'W2:0,3']
    assert errors == []


def test_a_locked_member_is_still_refused_with_its_message(page):
    """A redraw open on S1-2: when W2 is locked, its cabinet is refused and
    the toast names it, the path does not move. With the whole wall locked
    the circuit cannot be taken over at all."""
    pg, errors = page
    _open(pg, 'wall')
    _click(pg, 'W1', 2, 1, alt=True)
    _click(pg, 'W2', 0, 0)
    before = _path(pg, 'W1', 2)
    pg.evaluate("() => { window.__gw.L('W2').locked = true; window.__gw.clearToasts(); }")
    _click(pg, 'W2', 0, 1)
    assert _path(pg, 'W1', 2) == before
    assert 'W2 is locked. Unlock it to change it.' in _toasts(pg), _toasts(pg)
    pg.keyboard.press('Escape')
    _settle(pg)

    _open(pg, 'wall')
    pg.evaluate("() => { window.app.project.layers.forEach(l => { l.locked = true; }); }")
    _click(pg, 'W2', 0, 1, alt=True)
    assert pg.evaluate("() => window.app.getOverrideNums(window.__gw.L('W1'), 'power')") == []
    assert any('is locked' in t for t in _toasts(pg)), _toasts(pg)
    assert errors == []


# ── Older shows: one wall, or per member (the owner's option C) ──────────
#
# A show saved before this build walked a wall across processor canvases
# per member. As it opens, each group with no stored answer is decided
# once and the answer stored on the group (`powerPerMember`): it walks as
# one, unless a member after the first has its own circuits wired up
# (feeds, labels, cables, redraws, custom paths) or the group is locked.
# A group made in this build always walks as one. The answer is never read
# again off the members, so the wall does not flip later.

OPEN_JS = r"""async ({ edit, text }) => {
    const app = window.app, g = window.__gw;
    await app._layerSavesSettled();
    let project;
    if (text) project = JSON.parse(text);
    else {
        project = Object.assign({ name: 'Older wall', cableUnit: 'ft', app_version: '1.6.0-beta.5',
            distros: [{ id: 'd1', name: 'PD', ratingA: 400, system: '120/208', voltage: 208, phase: 3 }] },
            g.wall());
        // an older show's groups carry no answer
        project.groups.forEach(x => { delete x.powerPerMember; });
        const L = n => project.layers.find(l => l.name === n);
        if (edit === 'feeds') Object.assign(L('W2'), { powerSocaDistro: { '1': 'd1' }, powerSocaNumber: { '1': 3 } });
        if (edit === 'labels') L('W3').powerLabelOverrides = { '1': 'LEFT A' };
        if (edit === 'paths') Object.assign(L('W2'), {
            powerCustomOverrides: [1], powerCustomPaths: { '1': [{ row: 0, col: 0 }] } });
        if (edit === 'locked') project.layers.forEach(l => { l.locked = true; });
        if (edit === 'loose') { project.groups = []; project.layers.forEach(l => { l.group_id = null; }); }
    }
    await app._openProjectData(project, { source: 'file' });
    window.canvasRenderer.render();
    return true;
}"""


def _open_show(pg, edit=None, text=None):
    pg.evaluate(OPEN_JS, {'edit': edit, 'text': text})
    pg.wait_for_function("() => window.app._initialLoadComplete && !window.app._projectOpening")
    _settle(pg)


def _flag(pg):
    return pg.evaluate("() => (window.app.project.groups || []).map(g => g.powerPerMember)")


def _server_flag():
    import app as app_module
    return [g.get('powerPerMember') for g in (app_module.current_project.get('groups') or [])]


def _per_member(circuits):
    """Every member walks its own circuits (each starts at W*:0)."""
    return all(circuits[n] and circuits[n][0]['cols'][0] == f'{n}:0' for n in ('W1', 'W2', 'W3'))


def _as_one(circuits):
    return (len(circuits['W1']) == 6 and circuits['W2'] == [] and circuits['W3'] == []
            and circuits['W1'][1]['cols'] == ['W1:2', 'W2:0'])


@pytest.mark.parametrize('edit', ['feeds', 'labels', 'paths'])
def test_an_older_wall_with_its_own_circuits_wired_on_a_later_member_keeps_them(page, edit):
    """W2 on a distro, W3 with a typed circuit label, or W2 with a redraw:
    the wall keeps its per-member circuits, and the answer is stored on
    the group, on the server too."""
    pg, errors = page
    _open_show(pg, edit)
    assert _flag(pg) == [True]
    assert _server_flag() == [True]
    c = _circuits(pg)
    assert _per_member(c), c
    assert errors == []


def test_an_older_wall_with_nothing_wired_on_later_members_walks_as_one(page):
    pg, errors = page
    _open_show(pg)
    assert _flag(pg) == [False]
    assert _server_flag() == [False]
    c = _circuits(pg)
    assert _as_one(c), c
    assert errors == []


def test_an_older_locked_wall_never_changes_on_open(page):
    pg, errors = page
    _open_show(pg, 'locked')
    assert _flag(pg) == [True]
    c = _circuits(pg)
    assert _per_member(c), c
    assert [x['label'] for x in c['W2']] == ['S1-1', 'S1-2', 'S1-3'], c
    assert errors == []


def _select_all(pg):
    pg.evaluate("""() => { const app = window.app;
        app.selectedLayerIds = new Set(app.project.layers.map(l => l.id));
        app.currentLayer = app.project.layers[0]; }""")


def test_a_new_group_walks_as_one_and_undo_takes_it_back(page):
    """Three loose screens, W2 on a distro: grouped now, they walk as one
    (a new group always does). Undo ungroups them, redo groups them as one
    again."""
    pg, errors = page
    _open_show(pg, 'loose')
    pg.evaluate("""() => { const l = window.__gw.L('W2');
        l.powerSocaDistro = { '1': 'd1' }; }""")
    _select_all(pg)
    pg.evaluate("async () => { await window.app.groupSelectedLayers(); }")
    _settle(pg)
    assert _flag(pg) == [False]
    assert _server_flag() == [False]
    assert _as_one(_circuits(pg))
    _undo(pg)
    assert pg.evaluate("() => (window.app.project.groups || []).length") == 0
    assert _per_member(_circuits(pg))
    pg.evaluate("() => window.app.redo()")
    _settle(pg)
    assert _flag(pg) == [False]
    assert _as_one(_circuits(pg))
    assert errors == []


def test_the_answer_is_saved_and_never_read_again_off_the_members(page):
    """Saved and opened again, each wall keeps its stored answer, even
    when what decided it has changed since: the per-member wall with its
    feed taken off stays per member, the one-wall show with a feed added
    on W2 stays one wall. Nothing flips under the user."""
    pg, errors = page
    _open_show(pg, 'feeds')
    text = pg.evaluate("() => window.app.serializeProjectForFile()")
    import json
    saved = json.loads(text)
    assert [g.get('powerPerMember') for g in saved['groups']] == [True]
    for l in saved['layers']:
        l['powerSocaDistro'] = {}
        l['powerSocaNumber'] = {}
    _open_show(pg, text=json.dumps(saved))
    assert _flag(pg) == [True]
    assert _per_member(_circuits(pg))

    _open_show(pg)
    saved = json.loads(pg.evaluate("() => window.app.serializeProjectForFile()"))
    assert [g.get('powerPerMember') for g in saved['groups']] == [False]
    next(l for l in saved['layers'] if l['name'] == 'W2')['powerSocaDistro'] = {'1': 'd1'}
    _open_show(pg, text=json.dumps(saved))
    assert _flag(pg) == [False]
    assert _as_one(_circuits(pg))
    assert errors == []


def test_ungroup_and_group_again_is_a_new_group_and_undo_restores_the_old(page):
    """The per-member wall ungrouped and grouped again walks as one (a new
    group). Undo, twice, gives back the old group with its stored answer
    and its per-member circuits."""
    pg, errors = page
    _open_show(pg, 'feeds')
    assert _flag(pg) == [True]
    _select_all(pg)
    pg.evaluate("async () => { await window.app.ungroupSelectedLayers(); }")
    _settle(pg)
    _select_all(pg)
    pg.evaluate("async () => { await window.app.groupSelectedLayers(); }")
    _settle(pg)
    assert _flag(pg) == [False]
    assert _as_one(_circuits(pg))
    _undo(pg)
    assert _flag(pg) == []
    _undo(pg)
    assert _flag(pg) == [True]
    assert _per_member(_circuits(pg))
    assert _server_flag() == [True]
    assert errors == []
