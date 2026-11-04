"""2fers and 3fers through the take-over, custom mode and the batch verb.

The owner's rulings, 2026-10-19, on a wall of single-column runs that auto
splits into 3fers (each circuit three 5-cabinet columns, the lone last
column a circuit of its own):

1. Turning custom ON wipes every circuit on the screens it turns, starting
   empty - hand take-overs included. Staying in AUTO, one circuit can be
   taken over (Alt+click); a take-over of a SHARED circuit keeps its runs,
   so a 3fer stays three runs on the one circuit and still draws and tags
   as a 3fer. (It used to become one run of 15 and stop drawing.)
2. A custom fill with splitters on behaves the same as auto: a selection
   of three columns is one 3fer of three single-column runs (maxWays 2:
   2fers). (It used to be ONE custom path of 15 cabinets.)
3. The batch verb ("3fer this screen", "2fer them") never builds an OVER
   gang, in auto or custom: it joins runs only while their load fits the
   circuit - the amps figure the OVER flag reads - and leftovers, and runs
   too big to share, stay on circuits of their own. (It used to join by
   count alone: 15-cabinet circuits in threes, every gang OVER, and the
   lone column pulled into a gang.)
4. Alt-sweep + right-click -> 2fer / 3fer works on runs picked out by hand
   in auto (a taken-over circuit inside the sweep used to corrupt the
   deal), in custom, and across the members of a screen group.

Every test drives the real app on the shared e2e server with a synthetic
wall: 150 W cabinets on 208 V x 20 A, so one circuit carries 27 cabinets
and three 5-cabinet columns (2250 W) share one through a 3fer.

Run locally:
    python -m pytest tests/test_nfer_custom_rulings.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Counts the page's fetches until each reply's body is read (the dock
# tests' counter): "landed" waits on the requests a gesture started, the
# debounced history snapshot and the dock's layout pass - never the clock.
FETCH_COUNT_JS = """(() => {
    const orig = window.fetch;
    window.__lrdFetches = 0;
    window.fetch = function (...args) {
        window.__lrdFetches++;
        const sent = orig.apply(this, args);
        const done = () => setTimeout(() => { window.__lrdFetches--; }, 0);
        sent.then(r => r.clone().text().then(done, done), done);
        return sent;
    };
})()"""

QUIET_JS = """() => {
    const app = window.app;
    const idle = window.__lrdFetches === 0 && !app._saveStateTimer
        && !app._dockMasonryRaf;
    window.__lrdQuiet = idle ? (window.__lrdQuiet || 0) + 1 : 0;
    return window.__lrdQuiet >= 2;
}"""


def landed(page):
    page.evaluate("() => { window.__lrdQuiet = 0; }")
    page.wait_for_function(QUIET_JS)


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    context.add_init_script(FETCH_COUNT_JS)
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app._initialLoadComplete"
                         " === true && window.app._socketConnects >= 1")
    landed(pg)
    pg.evaluate(HELPERS_JS)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_function("() => window.canvasRenderer.viewMode === 'power'")
    landed(pg)
    pg._nf_errors = errors
    yield pg
    context.close()


HELPERS_JS = r"""
window.__nf = {
    async j(method, url, body) {
        const res = await fetch(url, {
            method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        return res.json();
    },
    // Screens from specs [{ name, columns, x, props }], 5 rows of 150 W
    // cabinets on 208 V x 20 A, cabled top-down (tl-v), Organized, sharing
    // through splitters (maxWays 3 unless the spec says), grouped as one
    // wall when `group` is set.
    async make(specs, opts) {
        const app = window.app, r = window.canvasRenderer;
        const o = Object.assign({ group: false, maxWays: 3 }, opts || {});
        await window.app._layerSavesSettled();
        await fetch('/api/project/new', { method: 'POST' });
        const ids = [];
        for (const s of specs) {
            const made = await this.j('POST', '/api/layer/add', {
                name: s.name, columns: s.columns, rows: 5,
                cabinet_width: 200, cabinet_height: 200,
                offset_x: s.x || 0, offset_y: 0 });
            ids.push(made.id);
        }
        const shape = (l, s) => Object.assign(l, {
            powerFlowPattern: 'tl-v', lastPowerFlowPattern: 'tl-v',
            powerCustomPath: false, powerOrganized: true, powerMaximize: false,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 150,
            powerCustomPaths: {}, powerCustomIndex: 1, powerCustomOverrides: [],
            powerSplitters: { enabled: true, maxWays: o.maxWays,
                              manual: { merge: [], split: [] } },
            locked: false,
        }, o.group ? { group_id: 'gN' } : {}, s.props || {});
        // `blank`: [[row, col], ...] cabinets that draw no power.
        const apply = (layers) => specs.forEach((s, i) => {
            const l = layers.find(x => x.id === ids[i]);
            if (!l) return;
            shape(l, s);
            (s.blank || []).forEach(([r, c]) => l.panels.forEach(p => {
                if (p.row === r && p.col === c) p.blank = true;
            }));
        });
        const p = await this.j('GET', '/api/project');
        apply(p.layers);
        p.groups = o.group ? [{ id: 'gN', name: 'WALL', layer_ids: ids }] : [];
        await this.j('PUT', '/api/project', p);
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('nfer_custom_rulings');
        apply(app.project.layers);
        const first = app.project.layers.find(l => l.id === ids[0]);
        app.currentLayer = first;
        app.selectedLayerIds = new Set([first.id]);
        app.lastSelectedLayerId = first.id;
        app._overrideEditing = null;
        app._sweepSelection = null;
        app._customToggleLast = {};
        if (app.powerCustomSelection) app.powerCustomSelection.clear();
        app._circuitTailCache = null;
        r.zoom = 0.3; r.panX = 40; r.panY = 60;
        app.renderLayers();
        app.loadLayerToInputs();
        app.resetHistory('Initial State');
        r.render();
        return ids;
    },
    layer(id) { return window.app.project.layers.find(l => l.id === id); },
    // The screen's circuits as the app reads them: number, run ids, the
    // cabinet count of each run, and the screens its cabinets sit on.
    circuits(id) {
        const app = window.app;
        app._circuitTailCache = null;
        return app.screenCircuits(this.layer(id)).map(c => ({
            num: c.num, runIds: c.runIds || null,
            runs: (c.branches || [c.panels]).map(b => b.length),
            on: [...new Set((c.layers || []).map(l => l.id))],
        }));
    },
    gangs(id) {
        window.app._circuitTailCache = null;
        return window.canvasRenderer._nferGangs(this.layer(id))
            .map(g => ({ num: g.num, ways: g.ways, over: g.over }));
    },
    manual(id) {
        const m = window.app.getPowerSplitters(this.layer(id)).manual;
        return { merge: m.merge, split: m.split, space: m.space };
    },
    // Every "Nfer" pill the power view paints in one frame.
    tags() {
        const r = window.canvasRenderer, ctx = r.ctx, oT = ctx.fillText;
        const texts = [];
        ctx.fillText = function (t, x, y, w) {
            if (/\dfer/.test(String(t))) texts.push(String(t));
            return oT.call(ctx, t, x, y, w);
        };
        window.app._circuitTailCache = null;
        try { r.render(); } finally { ctx.fillText = oT; }
        return texts;
    },
    // The client point at the middle of cabinet (row, col) of a screen.
    point(id, row, col) {
        const app = window.app, r = window.canvasRenderer;
        const layer = this.layer(id);
        const p = app.getPanelByRowCol(layer, row, col);
        const { dx, dy } = r.getLayerRenderOffset(layer);
        const off = r._layerCanvasOffset(layer);
        const wx = p.x + p.width / 2 + dx + off.wx;
        const wy = p.y + p.height / 2 + dy + off.wy;
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + wx * r.zoom + r.panX,
                 y: rect.top + wy * r.zoom + r.panY };
    },
    // The selection a marquee over columns c0..c1 of each screen makes:
    // spans [[layerId, c0, c1], ...].
    select(spans) {
        const app = window.app;
        app.powerCustomSelection.clear();
        spans.forEach(([id, c0, c1]) => this.layer(id).panels.forEach(p => {
            if (p.col >= c0 && p.col <= c1) {
                app.powerCustomSelection.add(app.getScopedPanelKey(id, p));
            }
        }));
        return app.powerCustomSelection.size;
    },
    history() { return window.app.history.map(h => h.action); },
};
"""

BATCH_ITEMS_JS = """() => {
    const menu = document.getElementById('context-menu');
    const vis = el => el && el.style.display !== 'none';
    const grab = a => {
        const el = menu.querySelector(`[data-action="${a}"]`);
        return el && vis(el) ? { label: (el.textContent || '').trim(),
            title: el.title,
            disabled: el.classList.contains('menu-disabled') } : null;
    };
    return { shown: !!menu && menu.style.display === 'block',
             n0: grab('hw-batch-n0'), n1: grab('hw-batch-n1'),
             n2: grab('hw-batch-n2') };
}"""


def make(page, specs, **opts):
    ids = page.evaluate("([s, o]) => window.__nf.make(s, o)", [specs, opts])
    landed(page)
    return ids


def pt(page, layer_id, row, col):
    return page.evaluate("([id, r, c]) => window.__nf.point(id, r, c)",
                         [layer_id, row, col])


def alt_click(page, p):
    page.keyboard.down('Alt')
    page.mouse.move(p['x'], p['y'])
    page.mouse.down()
    page.mouse.up()
    page.keyboard.up('Alt')
    landed(page)


def alt_sweep(page, a, b):
    page.keyboard.down('Alt')
    page.mouse.move(a['x'], a['y'])
    page.mouse.down()
    page.mouse.move((a['x'] + b['x']) / 2, (a['y'] + b['y']) / 2, steps=5)
    page.mouse.move(b['x'], b['y'], steps=5)
    page.mouse.up()
    page.keyboard.up('Alt')
    landed(page)


def menu_at(page, p):
    page.mouse.click(p['x'], p['y'], button='right')
    landed(page)
    return page.evaluate(BATCH_ITEMS_JS)


def take(page, action):
    page.locator(f'#context-menu [data-action="{action}"]').click()
    landed(page)


def custom_on(page):
    """The Power custom box, clicked the way a user clicks it."""
    page.locator('#power-custom-toggle').click()
    landed(page)


def fill(page, spans):
    """Select columns c0..c1 of each screen ([(layerId, c0, c1), ...]) and
    apply the top-down pattern - the fill the pattern tile runs on a
    selection."""
    n = page.evaluate("(spans) => window.__nf.select(spans)",
                      [list(x) for x in spans])
    assert n > 0
    ok = page.evaluate(
        "() => window.app._applyPatternFill('power', 'tl-v')")
    landed(page)
    return ok


def circuits(page, layer_id):
    return page.evaluate("(id) => window.__nf.circuits(id)", layer_id)


def gangs(page, layer_id):
    return page.evaluate("(id) => window.__nf.gangs(id)", layer_id)


def manual(page, layer_id):
    return page.evaluate("(id) => window.__nf.manual(id)", layer_id)


def history(page):
    return page.evaluate("() => window.__nf.history()")


# ── 1. the take-over keeps a shared circuit's runs ────────────────────────

def test_taking_over_a_3fer_keeps_its_three_runs(page):
    """Ten single-column runs at maxWays 3: auto makes 3fers of columns
    1-3, 4-6, 7-9 and leaves column 10 plain. Alt+click on circuit 2 takes
    it over: it stays three 5-cabinet runs, the wall still reads three
    3fers (bracket registry and painted pills), the drawing round-trips
    through the server with its run heads, and the take-over is ONE
    history entry."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    before = circuits(page, wall)
    assert [c['runs'] for c in before] == [[5, 5, 5]] * 3 + [[5]], before

    h0 = len(history(page))
    alt_click(page, pt(page, wall, 0, 4))
    landed(page)
    out = circuits(page, wall)
    c2 = next(c for c in out if c['num'] == 2)
    assert c2['runs'] == [5, 5, 5], (
        f'the taken-over 3fer must keep its three runs: {out}')
    assert c2['runIds'] and len(c2['runIds']) == 3, out
    assert page.evaluate("(id) => window.app.isRunOverridden("
                         "window.__nf.layer(id), 'power', 2)", wall)
    assert [g['num'] for g in gangs(page, wall)] == [1, 2, 3], gangs(page, wall)
    assert all(g['ways'] == 3 and not g['over'] for g in gangs(page, wall))
    assert page.evaluate("() => window.__nf.tags()").count('3fer') == 3, (
        'the taken-over 3fer must still wear its tag')
    assert history(page)[h0:] == ['Override Circuit'], history(page)

    saved = page.evaluate("""async (id) => {
        await window.app._layerSavesSettled();
        const p = await (await fetch('/api/project')).json();
        const l = p.layers.find(x => x.id === id);
        return (l.powerCustomPaths[2] || []).map(e => !!e.branch);
    }""", wall)
    assert len(saved) == 15 and [i for i, b in enumerate(saved) if b] == [5, 10], (
        f'the server must keep the run heads of the taken-over 3fer: {saved}')

    page.evaluate("() => window.app.undo()")
    landed(page)
    assert circuits(page, wall) == before, 'one undo puts the auto 3fer back'


def test_a_take_over_ended_unchanged_goes_back_to_auto(page):
    """The owner, 2026-11-03: a redraw that ends with the circuit's
    cabinets unchanged never stays a frozen override. Esc on the taken-over
    3fer with nothing redrawn: the 3fer is the automatic one again, as its
    own history step."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    before = circuits(page, wall)
    h0 = len(history(page))
    alt_click(page, pt(page, wall, 0, 4))
    landed(page)
    assert page.evaluate("(id) => window.app.isRunOverridden("
                         "window.__nf.layer(id), 'power', 2)", wall)
    page.keyboard.press('Escape')
    landed(page)
    assert not page.evaluate("(id) => window.app.isRunOverridden("
                             "window.__nf.layer(id), 'power', 2)", wall)
    assert circuits(page, wall) == before
    assert history(page)[h0:] == ['Override Circuit', 'Return Circuit To Auto'], history(page)


def test_taking_over_a_plain_circuit_stays_one_run(page):
    """The lone last column is a plain circuit; taken over, it is still
    one run and carries no tag."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    alt_click(page, pt(page, wall, 2, 9))
    landed(page)
    c4 = next(c for c in circuits(page, wall) if c['num'] == 4)
    assert c4['runs'] == [5] and c4['runIds'] is None, c4
    assert [g['num'] for g in gangs(page, wall)] == [1, 2, 3]


def test_taking_over_a_3fer_across_group_members_keeps_its_runs(page):
    """A two-screen group packs as one wall: circuit 2 is a 3fer of Left's
    last column and Right's first two. Taken over from a cabinet on Right,
    it stays three runs across both screens and still tags as a 3fer."""
    left, right = make(page, [{'name': 'Left', 'columns': 4},
                              {'name': 'Right', 'columns': 3, 'x': 800}],
                       group=True)
    alt_click(page, pt(page, right, 0, 1))
    page.keyboard.press('Escape')
    landed(page)
    c2 = next(c for c in circuits(page, left) if c['num'] == 2)
    assert c2['runs'] == [5, 5, 5], c2
    assert sorted(c2['on']) == sorted([left, right]), c2
    assert [g['num'] for g in gangs(page, left)] == [1, 2], gangs(page, left)


def test_a_fill_inside_a_taken_over_3fer_keeps_it_shared(page):
    """The taken-over 3fer is open for redrawing; a 3-column selection
    filled into it is one circuit of three column runs again - the take-
    over's own shape, on its one number - not one run of 15."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    alt_click(page, pt(page, wall, 0, 4))
    assert page.evaluate("() => !!window.app._overrideEditing")
    assert fill(page, [(wall, 3, 5)])
    c2 = next(c for c in circuits(page, wall) if c['num'] == 2)
    assert c2['runs'] == [5, 5, 5] and len(c2['runIds']) == 3, c2
    assert manual(page, wall)['merge'] == [], (
        'a taken-over circuit carries its runs on its path, not as merges')


# ── 1. custom ON starts empty ─────────────────────────────────────────────

def test_custom_on_wipes_every_circuit_and_take_over(page):
    """A screen with a taken-over circuit, a drawn path kept from an
    earlier custom spell and a share stored against those custom numbers:
    the custom box turns it custom with NOTHING drawn - no paths, no
    overrides, no custom shares, the active circuit back to 1 - in the
    toggle's one history entry, saved to the server."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    alt_click(page, pt(page, wall, 0, 4))
    page.keyboard.press('Escape')
    landed(page)
    page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        l.powerCustomPaths[7] = [{ row: 0, col: 9 }, { row: 1, col: 9 }];
        l.powerSplitters = { enabled: true, maxWays: 3,
            manual: { merge: [[7, 8]], split: [], space: 'custom' } };
        app.updateLayers([l]);
        app.resetHistory('Seeded');
    }""", wall)
    landed(page)
    h0 = len(history(page))
    custom_on(page)
    out = page.evaluate("""async (id) => {
        const l = window.__nf.layer(id);
        await window.app._layerSavesSettled();
        const p = await (await fetch('/api/project')).json();
        const s = p.layers.find(x => x.id === id);
        return { pattern: l.powerFlowPattern, paths: l.powerCustomPaths,
                 overrides: l.powerCustomOverrides, index: l.powerCustomIndex,
                 merge: window.app.getPowerSplitters(l).manual.merge,
                 savedPaths: s.powerCustomPaths,
                 savedOverrides: s.powerCustomOverrides };
    }""", wall)
    assert out['pattern'] == 'custom', out
    assert out['paths'] == {} and out['overrides'] == [], (
        f'custom ON must start with no circuits at all: {out}')
    assert out['index'] == 1 and out['merge'] == [], out
    assert out['savedPaths'] == {} and out['savedOverrides'] == [], out
    assert history(page)[h0:] == ['Power Custom Mode Toggle'], history(page)


def test_custom_on_wipes_the_labels_typed_by_hand(page):
    """The owner's ruling, 2026-10-19: custom ON also forgets the circuit
    labels typed by hand on the screens it turns, in the toggle's one
    history entry; a locked screen keeps its labels."""
    left, right = make(page, [{'name': 'Left', 'columns': 4},
                              {'name': 'Right', 'columns': 3, 'x': 800}])
    page.evaluate("""([a, b]) => {
        const app = window.app;
        const L = window.__nf.layer(a), R = window.__nf.layer(b);
        L.powerLabelOverrides = { 1: 'HOUSE L', 2: 'HOUSE L2' };
        R.powerLabelOverrides = { 1: 'KEEP ME' };
        R.locked = true;
        app._showLockedError = () => {};
        app.selectedLayerIds = new Set([a, b]);
        app.updateLayers([L, R]);
        app.resetHistory('Seeded');
    }""", [left, right])
    landed(page)
    h0 = len(history(page))
    custom_on(page)
    out = page.evaluate("""async ([a, b]) => {
        await window.app._layerSavesSettled();
        const p = await (await fetch('/api/project')).json();
        const saved = (id) => p.layers.find(x => x.id === id).powerLabelOverrides;
        return { left: window.__nf.layer(a).powerLabelOverrides,
                 right: window.__nf.layer(b).powerLabelOverrides,
                 savedLeft: saved(a) };
    }""", [left, right])
    assert out['left'] == {} and out['savedLeft'] == {}, out
    assert out['right'] == {'1': 'KEEP ME'}, out
    assert history(page)[h0:] == ['Power Custom Mode Toggle'], history(page)


def test_custom_on_keeps_a_run_across_a_locked_member(page):
    """A locked screen is never changed: a path the open screen drew onto
    its locked neighbour's cabinets stays when custom goes on, and the
    locked screen is named. Round 6: Left and Right are a half-locked group
    (an old file's), locked as a whole until the user picks Lock or Unlock,
    so Left keeps all its runs too."""
    left, right = make(page, [{'name': 'Left', 'columns': 4},
                              {'name': 'Right', 'columns': 3, 'x': 800}],
                       group=True)
    page.evaluate("""([a, b]) => {
        const app = window.app;
        const L = window.__nf.layer(a), R = window.__nf.layer(b);
        L.powerCustomPaths = { 9: [{ row: 0, col: 3 },
                                   { row: 0, col: 0, layerId: b }],
                               10: [{ row: 4, col: 0 }] };
        R.locked = true;
        window.__nf.errors = [];
        app._showLockedError = (ls) => { if (ls && ls.length)
            window.__nf.errors.push(window.app._lockedErrorNames(ls)); };
        app.updateLayers([L, R]);
        app.resetHistory('Seeded');
    }""", [left, right])
    landed(page)
    custom_on(page)
    out = page.evaluate("""(a) => ({
        paths: Object.keys(window.__nf.layer(a).powerCustomPaths),
        errors: window.__nf.errors })""", left)
    assert out['paths'] == ['9', '10'], (
        f'the half-locked group changed: {out}')
    assert ['Right'] in out['errors'], out


# ── 2. custom fill shares like auto ───────────────────────────────────────

def test_custom_fill_of_three_columns_is_one_3fer(page):
    """Custom on (empty), a 3-column selection filled: three single-column
    custom runs shared as ONE 3fer - not one path of 15 - in one history
    entry. Six columns make two 3fers."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    custom_on(page)
    h0 = len(history(page))
    assert fill(page, [(wall, 0, 2)])
    out = circuits(page, wall)
    assert out == [{'num': 1, 'runIds': [1, 2, 3], 'runs': [5, 5, 5],
                    'on': [wall]}], (
        f'a 3-column fill must be one 3fer of three column runs: {out}')
    assert manual(page, wall) == {'merge': [[1, 2, 3]], 'split': [],
                                  'space': 'custom'}
    assert gangs(page, wall) == [{'num': 1, 'ways': 3, 'over': False}]
    assert history(page)[h0:] == ['Power Custom Pattern Apply'], history(page)

    page.evaluate("() => { window.app.currentLayer.powerCustomIndex = 4; }")
    assert fill(page, [(wall, 3, 8)])
    assert [c['runs'] for c in circuits(page, wall)] == [[5, 5, 5]] * 3
    assert [g['ways'] for g in gangs(page, wall)] == [3, 3, 3]


def test_custom_fill_with_2fers_pairs_runs(page):
    """maxWays 2: the same 3-column selection is a 2fer and a plain run -
    what auto makes of that block."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}], maxWays=2)
    custom_on(page)
    assert fill(page, [(wall, 0, 2)])
    out = circuits(page, wall)
    assert [(c['num'], c['runs']) for c in out] == [(1, [5, 5]), (3, [5])], out
    assert manual(page, wall)['merge'] == [[1, 2]]


def test_custom_refill_drops_the_old_gangs(page):
    """Refilling numbers that were in a gang re-deals them: the old merge
    does not outlive the drawing it described."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    custom_on(page)
    assert fill(page, [(wall, 0, 2)])
    page.evaluate("() => { window.app.currentLayer.powerCustomIndex = 2; }")
    assert fill(page, [(wall, 3, 3)])
    assert manual(page, wall)['merge'] == [], manual(page, wall)
    assert [(c['num'], c['runs']) for c in circuits(page, wall)] == [
        (1, [5]), (2, [5]), (3, [5])], circuits(page, wall)


# ── 3. the batch verb never builds an OVER gang ───────────────────────────

def test_batch_3fer_screen_leaves_the_lone_column_plain(page):
    """Custom, ten single-column circuits drawn plain: "3fer this screen"
    deals what auto deals - three 3fers and the lone last column on a
    circuit of its own with no tag."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    custom_on(page)
    page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        for (let c = 0; c < 10; c++) {
            l.powerCustomPaths[c + 1] = [0, 1, 2, 3, 4].map(r => ({ row: r, col: c }));
        }
        app.updateLayers([l]);
        app.resetHistory('Seeded');
    }""", wall)
    landed(page)
    items = menu_at(page, pt(page, wall, 0, 0))
    assert items['n1'] and items['n1']['label'] == (
        '3fer this screen (3 × 3fer + 1 plain)'), items
    assert not items['n1']['disabled'], items
    take(page, 'hw-batch-n1')
    assert manual(page, wall)['merge'] == [[1, 2, 3], [4, 5, 6], [7, 8, 9]], (
        manual(page, wall))
    assert [g['ways'] for g in gangs(page, wall)] == [3, 3, 3]
    assert not any(g['over'] for g in gangs(page, wall))
    assert history(page)[-1] == '3fer Screen'


def test_batch_never_gangs_circuits_too_big_to_share(page):
    """Custom, circuits already three columns each (15 cabinets, 2250 W)
    and a lone column. The owner's clarification, 2026-10-19 ("i am taking
    3 columns and 1 port and making it 3fer the single port"): a circuit
    that spans three columns as one run is split into its own three legs
    - "3fer this screen" makes three 3fers and leaves the lone column
    plain - and is never joined with a neighbour: "2fer this screen" has
    no circuit that fits a 2fer and joins nothing (it used to gang the
    last 3-column circuit with the lone column), so it stays on the menu
    disabled. Never a 45-cabinet OVER gang either way."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    custom_on(page)
    page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        const col = (c) => [0, 1, 2, 3, 4].map(r => ({ row: r, col: c }));
        l.powerCustomPaths = { 1: [0, 1, 2].flatMap(col),
                               2: [3, 4, 5].flatMap(col),
                               3: [6, 7, 8].flatMap(col), 4: col(9) };
        app.updateLayers([l]);
        app.resetHistory('Seeded');
    }""", wall)
    landed(page)
    items = menu_at(page, pt(page, wall, 0, 0))
    entries = [e for e in (items['n0'], items['n1']) if e]
    assert entries and all('OVER' not in e['title'] for e in entries), items
    assert items['n0'] and items['n0']['disabled'], items
    assert items['n0']['label'] == '2fer this screen (4 plain)', items
    assert items['n1'] and items['n1']['label'] == (
        '3fer this screen (3 × 3fer + 1 plain)'), items
    assert not items['n1']['disabled'], items
    take(page, 'hw-batch-n1')
    out = circuits(page, wall)
    assert [c['runs'] for c in out] == [[5, 5, 5]] * 3 + [[5]], out
    assert [g['ways'] for g in gangs(page, wall)] == [3, 3, 3], gangs(page, wall)
    assert not any(g['over'] for g in gangs(page, wall)), gangs(page, wall)


def test_batch_with_nothing_that_fits_is_disabled_with_the_reason(page):
    """Custom, every circuit 15 cabinets across three columns: none fits a
    2fer and none is joined to another (the owner's clarification,
    2026-10-19), so "2fer this screen" shares nothing - it stays on the
    menu disabled, naming the circuits and why, and a click writes
    nothing. Single-column circuits too heavy to pair are refused by
    their load: the first pair and its amps are named."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 9}])
    custom_on(page)
    page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        const col = (c) => [0, 1, 2, 3, 4].map(r => ({ row: r, col: c }));
        l.powerCustomPaths = { 1: [0, 1, 2].flatMap(col),
                               2: [3, 4, 5].flatMap(col),
                               3: [6, 7, 8].flatMap(col) };
        app.updateLayers([l]);
        app.resetHistory('Seeded');
    }""", wall)
    landed(page)
    h0 = len(history(page))
    items = menu_at(page, pt(page, wall, 0, 0))
    assert items['n0'] and items['n0']['disabled'], items
    assert items['n0']['title'] == (
        'S1-1, S1-2 and S1-3 span more columns than a 2fer has ways. A '
        'circuit across several columns splits into its own legs and never '
        'joins another.'), items
    take(page, 'hw-batch-n0')
    assert manual(page, wall)['merge'] == [] and len(history(page)) == h0

    page.evaluate("window.app.hideContextMenu()")
    page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        const col = (c) => [0, 1, 2, 3, 4].map(r => ({ row: r, col: c }));
        l.powerAmperage = 7.5;
        l.powerCustomPaths = { 1: col(0), 2: col(1), 3: col(2) };
        app._circuitTailCache = null;
        app.updateLayers([l]);
        app.resetHistory('Seeded');
    }""", wall)
    landed(page)
    h0 = len(history(page))
    items = menu_at(page, pt(page, wall, 0, 0))
    assert items['n0'] and items['n0']['disabled'], items
    assert items['n0']['title'] == ('S1-1 and S1-2 together draw 7.2 A on a '
                                    '7.5 A circuit held to 6 A (80%), so no runs '
                                    'here fit on one circuit together'), items
    take(page, 'hw-batch-n0')
    assert manual(page, wall)['merge'] == [] and len(history(page)) == h0


def test_batch_in_auto_deals_what_fits_instead_of_refusing(page):
    """Auto at 10 A (2080 W, 80% of a 12.5 A breaker): two 750 W columns fit a circuit, three do
    not - except the first three, the first column being two blanks short
    (450 W). "3fer this screen" used to refuse the whole deal for the
    groups past the amps; now it deals the one 3fer that fits and pairs
    the rest, every group within the amps."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10,
                           'blank': [[3, 0], [4, 0]],
                           'props': {'powerAmperage': 12.5}}])
    page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        l.powerSplitters.manual = { merge: [], split: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] };
        app.updateLayers([l]);
        app.resetHistory('Seeded');
    }""", wall)
    landed(page)
    items = menu_at(page, pt(page, wall, 2, 1))
    three = items['n1']
    assert three and three['label'] == (
        '3fer this screen (1 × 3fer + 3 × 2fer + 1 plain)'), items
    assert not three['disabled'], items
    take(page, 'hw-batch-n1')
    m = manual(page, wall)
    assert m['merge'] == [[1, 2, 3], [4, 5], [6, 7], [8, 9]], m
    assert m['split'] == [10], m
    assert not any(g['over'] for g in gangs(page, wall)), gangs(page, wall)


# ── 4. Alt-sweep + right-click on runs picked by hand ─────────────────────

def test_sweep_over_a_taken_over_circuit_deals_only_real_runs(page):
    """Auto: circuit 2 (a 3fer) taken over, then a sweep over circuits
    1-3 and "2fer them". The taken-over circuit is a drawing, not a run:
    it keeps its three runs and breaks the line, and the runs either side
    deal on their own - 2fer + plain each side, the plain runs pinned.
    It used to deal circuit 2's NUMBER as run 2 - [[1, 2], [2, 3]]."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}], maxWays=3)
    # taken over and left open: ended unchanged it would go back to auto
    alt_click(page, pt(page, wall, 0, 4))
    landed(page)
    page.evaluate("() => window.app.resetHistory('Taken over')")
    alt_sweep(page, pt(page, wall, 2, 0), pt(page, wall, 2, 6))
    sel = page.evaluate("() => window.app._sweepSelection")
    assert sel and sel['nums'] == [1, 2, 3], sel
    items = menu_at(page, pt(page, wall, 2, 6))
    assert items['n0'] and items['n0']['label'] == (
        '2fer them (2 × 2fer + 2 plain)'), items
    take(page, 'hw-batch-n0')
    m = manual(page, wall)
    assert m['merge'] == [[1, 2], [4, 5]] and m['split'] == [3, 6], m
    c2 = next(c for c in circuits(page, wall) if c['num'] == 2)
    assert c2['runs'] == [5, 5, 5], c2
    assert history(page)[-1] == '2fer Selection'


def test_sweep_in_custom_re_deals_filled_3fers_as_2fers(page):
    """Custom: a 6-column fill is two 3fers of column runs; sweeping both
    circuits and taking "2fer them" deals the six runs as three 2fers,
    none OVER."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    custom_on(page)
    assert fill(page, [(wall, 0, 5)])
    alt_sweep(page, pt(page, wall, 2, 0), pt(page, wall, 2, 3))
    sel = page.evaluate("() => window.app._sweepSelection")
    assert sel and sel['nums'] == [1, 4], sel
    items = menu_at(page, pt(page, wall, 2, 3))
    assert items['n0'] and items['n0']['label'] == '2fer them (3 × 2fer)', items
    take(page, 'hw-batch-n0')
    assert manual(page, wall)['merge'] == [[1, 2], [3, 4], [5, 6]]
    assert [g['ways'] for g in gangs(page, wall)] == [2, 2, 2]
    assert not any(g['over'] for g in gangs(page, wall))


def test_sweep_across_group_members_in_custom(page):
    """A two-screen group in custom mode, one fill across all seven
    columns: 3fers of columns 1-3 and 4-6 (column 4 on Left, 5-6 on
    Right) and column 7 plain. A sweep over Right's circuits re-deals
    their runs as 2fers - runs crossing members, none OVER."""
    left, right = make(page, [{'name': 'Left', 'columns': 4},
                              {'name': 'Right', 'columns': 3, 'x': 800}],
                       group=True)
    page.evaluate("(ids) => { window.app.selectedLayerIds = new Set(ids); }",
                  [left, right])
    custom_on(page)
    assert fill(page, [(left, 0, 3), (right, 0, 2)])
    out = circuits(page, left)
    assert [(c['num'], c['runs']) for c in out] == [
        (1, [5, 5, 5]), (4, [5, 5, 5]), (7, [5])], out
    assert sorted(out[1]['on']) == sorted([left, right]), out
    alt_sweep(page, pt(page, right, 2, 1), pt(page, right, 2, 2))
    sel = page.evaluate("() => window.app._sweepSelection")
    assert sel and sel['layerId'] == left and sel['nums'] == [4, 7], sel
    items = menu_at(page, pt(page, right, 2, 2))
    assert items['n0'] and items['n0']['label'] == '2fer them (2 × 2fer)', items
    take(page, 'hw-batch-n0')
    assert manual(page, left)['merge'] == [[1, 2, 3], [4, 5], [6, 7]]
    assert not any(g['over'] for g in gangs(page, left))


def test_sweep_across_group_members_in_auto(page):
    """The same group in auto: circuit 2 crosses the members. A sweep over
    circuits 2 and 3 deals runs 4-7 as two 2fers."""
    left, right = make(page, [{'name': 'Left', 'columns': 4},
                              {'name': 'Right', 'columns': 3, 'x': 800}],
                       group=True)
    alt_sweep(page, pt(page, left, 2, 3), pt(page, right, 2, 2))
    sel = page.evaluate("() => window.app._sweepSelection")
    assert sel and sel['layerId'] == left and sel['nums'] == [2, 3], sel
    items = menu_at(page, pt(page, right, 2, 2))
    assert items['n0'] and items['n0']['label'] == '2fer them (2 × 2fer)', items
    take(page, 'hw-batch-n0')
    assert manual(page, left)['merge'] == [[4, 5], [6, 7]], manual(page, left)


# ── a clear on a taken-over circuit leaves the auto runs' shares alone ────

TAKEN_OVER_MULTI_JS = """(id) => {
    const app = window.app, l = window.__nf.layer(id);
    l.powerSocaSplits = [3];
    l.powerSplitters = { enabled: true, maxWays: 3,
        manual: { merge: [[4, 5, 6]], split: [], space: 'auto' } };
    app._circuitTailCache = null;
    app.updateLayers([l]);
    app.resetHistory('Seeded');
    const rec = app._powerNaming(l).socas.get(2);
    return rec ? rec.circuits : null;
}"""


def _taken_over_lone_column(page):
    """Ten columns, the lone last column (circuit 4) taken over, the wall
    split so that circuit is a multi of its own (multi 2), and a share
    stored against auto runs 4-6 - run 4 shares its ORDINAL with the
    taken-over circuit's number."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    alt_click(page, pt(page, wall, 2, 9))
    page.keyboard.press('Escape')
    landed(page)
    assert page.evaluate(TAKEN_OVER_MULTI_JS, wall) == [4]
    landed(page)
    assert manual(page, wall)['merge'] == [[4, 5, 6]]
    return wall


def test_clearing_a_taken_over_circuit_chip_keeps_the_auto_shares(page):
    """The dock's "Clear circuit" on the taken-over circuit: its number is
    a circuit number, not a run ordinal, so the auto 3fer of runs 4-6
    keeps its share. It used to be read as run 4 and wiped out of it."""
    wall = _taken_over_lone_column(page)
    page.evaluate("(id) => window.app._clearCircuitChip("
                  "window.__nf.layer(id), 2, 4)", wall)
    landed(page)
    assert history(page)[-1] == 'Unplug Circuit', history(page)
    assert manual(page, wall)['merge'] == [[4, 5, 6]], manual(page, wall)
    c2 = next(c for c in circuits(page, wall) if c['num'] == 2)
    assert c2['runs'] == [5, 5, 5], c2


def test_clearing_a_taken_over_circuits_multi_keeps_the_auto_shares(page):
    """The same through the multi clear (_clearMultis reads its run ids
    from _socaClearTargets)."""
    wall = _taken_over_lone_column(page)
    page.evaluate("(id) => window.app._clearMultis("
                  "[{ layerId: id, soca: 2 }], 'Clear Multi')", wall)
    landed(page)
    assert manual(page, wall)['merge'] == [[4, 5, 6]], manual(page, wall)
    c2 = next(c for c in circuits(page, wall) if c['num'] == 2)
    assert c2['runs'] == [5, 5, 5], c2


def test_a_taken_over_circuit_never_lends_its_load_to_an_auto_run(page):
    """The lone last column, two cabinets blank (3 live, 2.2 A), taken over
    as plain circuit 4; auto run 4 is a full column (3.6 A). The share
    figures read run 4 as the auto run: three full runs are 10.8 A, and
    on a 10 A circuit the batch deal pairs runs rather than building a
    10.8 A 3fer. The taken-over circuit's number used to overwrite run 4's
    figure with its own 2.2 A."""
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10,
                           'blank': [[3, 9], [4, 9]]}])
    # taken over and left open: ended unchanged it would go back to auto
    alt_click(page, pt(page, wall, 0, 9))
    landed(page)
    out = page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        app._circuitTailCache = null;
        const amps = app.shareLoad(l, [4, 5, 6]).amps;
        l.powerAmperage = 12.5;
        app._circuitTailCache = null;
        const nums = app.screenCircuits(l).map(c => c.num);
        const deal = app.batchShareGroups(l, nums, 3).groups;
        l.powerAmperage = 20;
        app._circuitTailCache = null;
        return { amps, nums, deal };
    }""", wall)
    assert abs(out['amps'] - 3 * 750 / 208) < 1e-6, out
    assert out['deal'] == [[1, 2], [3, 4], [5, 6], [7, 8], [9]], (
        f'no group may pass the 10 A circuit (80% of 12.5 A): {out}')


# ── custom mode: a group is ONE wall ───────────────────────────────────────
#
# The owner's ruling, 2026-10-19: "3 fers etc can fill across screens just
# like in auto when in a group. remember it's treated as one screen in this
# way." In custom mode the group's first member owns and numbers every
# circuit, whichever member is selected, so labels and multis run as one
# sequence for the wall. A run an old file left on another member is
# ADOPTED when a wall action shares it: it moves into the first member's
# numbering at the next number, its typed label, cable and distro slot
# forgotten the way a clear forgets them - one undoable entry. Mixed
# panel / wattage groups are one wall too. Locked members never change.

def _wall(page, right_props=None):
    left, right = make(page, [{'name': 'Left', 'columns': 4},
                              {'name': 'Right', 'columns': 3, 'x': 800,
                               'props': right_props or {}}],
                       group=True)
    page.evaluate("(ids) => { window.app.selectedLayerIds = new Set(ids); }",
                  [left, right])
    custom_on(page)
    return left, right


def _select(page, layer_id):
    page.evaluate("""(id) => {
        const app = window.app, l = window.__nf.layer(id);
        app.currentLayer = l;
        app.selectedLayerIds = new Set([id]);
        app.updateCustomPowerUI();
    }""", layer_id)


# Old-file shape: each member owns single-column runs of its own.
LEGACY_JS = """([a, b, extra]) => {
    const app = window.app;
    const L = window.__nf.layer(a), R = window.__nf.layer(b);
    const col = (c) => [0, 1, 2, 3, 4].map(r => ({ row: r, col: c }));
    L.powerCustomPaths = { 1: col(0), 2: col(1) };
    R.powerCustomPaths = { 1: col(0), 2: col(1) };
    Object.assign(R, extra || {});
    app.updateLayers([L, R]);
    app._circuitTailCache = null;
    app.resetHistory('Old file');
}"""


def _paths(page, layer_id):
    return page.evaluate("""(id) => {
        const p = window.__nf.layer(id).powerCustomPaths || {};
        const out = {};
        Object.keys(p).forEach(n => { if ((p[n] || []).length) out[n] =
            [...new Set(p[n].map(e => (e.layerId || id) + ':' + e.col))]; });
        return out;
    }""", layer_id)


def test_custom_group_fill_from_any_member_numbers_on_the_wall(page):
    """Custom on a group, the first member's columns filled, then the
    second member SELECTED and its columns filled after Next: the circuits
    land on the first member, numbering on from the wall's own - not a
    second numbering starting at 1 on the member."""
    left, right = _wall(page)
    _select(page, left)
    assert fill(page, [(left, 0, 2)])
    _select(page, right)
    page.evaluate("() => window.app.stepCustomPort(1)")
    landed(page)
    assert fill(page, [(right, 0, 2)])
    assert _paths(page, right) == {}, _paths(page, right)
    out = circuits(page, left)
    assert [(c['num'], c['runs']) for c in out] == [(1, [5, 5, 5]),
                                                    (4, [5, 5, 5])], out
    assert out[1]['on'] == [right], out
    assert circuits(page, right) == [], 'the wall owner reports the circuits'
    assert manual(page, left)['merge'] == [[1, 2, 3], [4, 5, 6]]


def test_custom_group_sweep_shares_runs_of_two_members(page):
    """An old file: each member owns two column runs. A sweep from the
    first member's circuit 2 onto the second member's circuit 1 and "2fer
    them": the member's run is adopted as the wall's circuit 3 and shared
    with circuit 2 - ONE history entry, and one undo puts the old file
    back."""
    left, right = _wall(page)
    page.evaluate(LEGACY_JS, [left, right, None])
    landed(page)
    h0 = len(history(page))
    alt_sweep(page, pt(page, left, 2, 1), pt(page, right, 2, 0))
    items = menu_at(page, pt(page, right, 2, 0))
    assert items['n0'] and items['n0']['label'] == '2fer them (1 × 2fer)', items
    take(page, 'hw-batch-n0')
    assert manual(page, left)['merge'] == [[2, 3]], manual(page, left)
    assert _paths(page, left)['3'] == [f'{right}:0'], _paths(page, left)
    assert _paths(page, right) == {'2': [f'{right}:1']}, _paths(page, right)
    assert history(page)[h0:] == ['2fer Selection'], history(page)
    page.evaluate("() => window.app.undo()")
    landed(page)
    assert sorted(_paths(page, right)) == ['1', '2'], _paths(page, right)
    assert sorted(_paths(page, left)) == ['1', '2'], _paths(page, left)


def test_custom_group_batch_button_deals_the_whole_wall(page):
    """The same old file, "2fer this screen" from the second member: the
    whole wall's runs deal - the member's runs adopted as circuits 3 and 4
    - into two 2fers."""
    left, right = _wall(page)
    page.evaluate(LEGACY_JS, [left, right, None])
    landed(page)
    items = menu_at(page, pt(page, right, 2, 1))
    assert items['n0'] and items['n0']['label'] == (
        '2fer this screen (2 × 2fer)'), items
    take(page, 'hw-batch-n0')
    assert manual(page, left)['merge'] == [[1, 2], [3, 4]], manual(page, left)
    assert _paths(page, right) == {}, _paths(page, right)
    assert [g['ways'] for g in gangs(page, left)] == [2, 2]


def test_custom_group_share_with_next_crosses_the_seam(page):
    """Right-click the first member's last circuit: "Share with next run"
    reaches the second member's first run, adopting it."""
    left, right = _wall(page)
    page.evaluate(LEGACY_JS, [left, right, None])
    landed(page)
    page.mouse.click(*pt(page, left, 2, 1).values(), button='right')
    landed(page)
    page.locator('#context-menu [data-action="hw-share"]').click()
    landed(page)
    assert manual(page, left)['merge'] == [[2, 3]], manual(page, left)
    assert _paths(page, left)['3'] == [f'{right}:0']


def test_adoption_forgets_the_runs_label_cable_and_distro_slot(page):
    """The adopted run's paperwork stays behind and goes, as a clear
    forgets it: its typed label, its cable and its place on the distro.
    The member's other circuit keeps its multi on the distro."""
    left, right = _wall(page)
    distro = page.evaluate(
        "() => window.app.addDistro({ name: 'PD' }).id")
    page.evaluate(LEGACY_JS, [left, right, {
        'powerLabelOverrides': {'1': 'RIGHT ONE'},
        'powerCircuitCables': {'1': {'ft': 25}},
        'powerSocaDistro': {'1': distro}, 'powerSocaNumber': {'1': 2}}])
    landed(page)
    alt_sweep(page, pt(page, left, 2, 1), pt(page, right, 2, 0))
    menu_at(page, pt(page, right, 2, 0))
    take(page, 'hw-batch-n0')
    out = page.evaluate("""([a, b, d]) => {
        const app = window.app, R = window.__nf.layer(b), L = window.__nf.layer(a);
        app._circuitTailCache = null;
        return { labels: R.powerLabelOverrides, cables: R.powerCircuitCables,
                 distros: Object.values(R.powerSocaDistro || {}),
                 adoptedLabel: app.getPowerCircuitLabel(L, 3) };
    }""", [left, right, distro])
    assert '1' not in (out['labels'] or {}), out
    assert '1' not in (out['cables'] or {}), out
    assert out['distros'] == [distro], (
        f"the member's remaining circuit keeps its multi on the box: {out}")
    assert out['adoptedLabel'] != 'RIGHT ONE', out


def test_custom_mixed_group_is_one_wall(page):
    """A group of two cabinet wattages (auto routes them apart): in custom
    it is one wall all the same - a fill from the second member numbers on
    the first, and a sweep shares across the seam."""
    left, right = _wall(page, right_props={'panelWatts': 100})
    _select(page, left)
    assert fill(page, [(left, 3, 3)])
    _select(page, right)
    page.evaluate("() => window.app.stepCustomPort(1)")
    landed(page)
    assert fill(page, [(right, 0, 1)])
    assert _paths(page, right) == {}
    assert [(c['num'], c['runs']) for c in circuits(page, left)] == [
        (1, [5]), (2, [5, 5])], circuits(page, left)
    alt_sweep(page, pt(page, left, 2, 3), pt(page, right, 2, 0))
    items = menu_at(page, pt(page, right, 2, 0))
    assert items['n1'] and items['n1']['label'] == '3fer them (1 × 3fer)', items
    take(page, 'hw-batch-n1')
    assert manual(page, left)['merge'] == [[1, 2, 3]], manual(page, left)


def test_alt_click_on_a_members_old_run_adopts_it(page):
    """Alt+click in custom on a run an old file left on the second member:
    it is adopted as the wall's next circuit and opened there, in one
    history entry."""
    left, right = _wall(page)
    page.evaluate(LEGACY_JS, [left, right, None])
    landed(page)
    h0 = len(history(page))
    alt_click(page, pt(page, right, 2, 0))
    out = page.evaluate("""(a) => ({ cur: window.app.currentLayer.id,
        idx: window.__nf.layer(a).powerCustomIndex })""", left)
    assert out == {'cur': left, 'idx': 3}, out
    assert _paths(page, left)['3'] == [f'{right}:0'], _paths(page, left)
    assert _paths(page, right) == {'2': [f'{right}:1']}, _paths(page, right)
    assert history(page)[h0:] == ['Adopt Circuit'], history(page)


def test_adopting_from_a_locked_member_is_refused(page):
    """A wall action that would adopt a locked member's run changes
    nothing - neither screen - and names the locked screen."""
    left, right = _wall(page)
    page.evaluate(LEGACY_JS, [left, right, {'locked': True}])
    page.evaluate("""() => { window.__nf.errors = [];
        window.app._showLockedError = (ls) => { if (ls && ls.length)
            window.__nf.errors.push(window.app._lockedErrorNames(ls)); }; }""")
    landed(page)
    h0 = len(history(page))
    items = menu_at(page, pt(page, left, 2, 0))
    take(page, 'hw-batch-n0')
    assert manual(page, left)['merge'] == [], manual(page, left)
    assert sorted(_paths(page, right)) == ['1', '2']
    assert len(history(page)) == h0
    assert ['Right'] in page.evaluate("() => window.__nf.errors"), items


def test_no_page_errors(page):
    assert page._nf_errors == [], page._nf_errors


# ── rows share too, on a wall cabled across ───────────────────────────────
# Owner, 2026-10-19: sharing "can [work] in rows if cabled horizontally".
# A row of 4 cabinets is 2.9 A, so rows fit three to a 20 A circuit.

def test_auto_shares_rows_on_a_wall_cabled_across(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 4, 'props': {
        'powerFlowPattern': 'tl-h', 'lastPowerFlowPattern': 'tl-h'}}])
    out = circuits(page, wall)
    runs = [r for c in out for r in c['runs']]
    assert runs == [4] * 5, f'each row must be a run of its own: {out}'
    assert out[0]['runs'] == [4, 4, 4], out
    assert all(not g['over'] for g in gangs(page, wall))
    assert gangs(page, wall)[0]['ways'] == 3


def test_custom_fill_across_makes_row_runs_that_share(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 4}])
    custom_on(page)
    n = page.evaluate("(spans) => window.__nf.select(spans)", [[wall, 0, 3]])
    assert n > 0
    assert page.evaluate(
        "() => window.app._applyPatternFill('power', 'tl-h')")
    landed(page)
    out = circuits(page, wall)
    runs = [r for c in out for r in c['runs']]
    assert runs == [4] * 5, f'a fill across must make a run per row: {out}'
    assert out[0]['runs'] == [4, 4, 4], out
    assert all(not g['over'] for g in gangs(page, wall))
