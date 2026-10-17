"""Custom mode: the load rule a custom port is judged by, and the warning a
partial group fill gives.

1. A CUSTOM PORT IS CHARGED THE WAY ITS BADGE CHARGES IT. NovaStar Armor
   pays for the pixel rectangle that encloses a port's cabinets (its
   reserved-rectangle rule); custom mode used to add up the cabinets
   instead, so an L along the top row and down the side of a 10 x 10 wall
   of 128 px cabinets took 19 cabinets onto a port whose badge read 248%.
   The click, the pattern fill's cut, the readout and the badge now use
   one load - the renderer's getPortPixelLoad - for every processor, and
   every other processor keeps its plain sum.
2. A PATTERN TILE ON SOME SCREENS OF A CUSTOM GROUP still redoes every run
   touching the selection as a whole (the owner's ruling, 2026-10-16:
   "Warn and do it"), and now names the screens it unwired: "Runs that
   crossed into Lower were redone - Lower's cabinets on them are now
   unwired." Power says circuits.

Run locally:
    python -m pytest tests/test_custom_audit_fixes.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
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
    pg.wait_for_function(
        "() => window.app && window.canvasRenderer && window.app.project"
        " && typeof window.app._layerSavesSettled === 'function'",
        timeout=20000)
    yield pg
    context.close()


HELPERS_JS = r"""
window.__fx = {
    toasts: [],
    async j(method, url, body) {
        const res = await fetch(url, {
            method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        return res.json();
    },
    async settle() {
        await window.app._layerSavesSettled();
        await new Promise(r => setTimeout(r, 0));
    },
    // Screens from specs [{ name, columns, rows, w, h, x, y, props }], all
    // in custom mode on both tabs, grouped as one wall when `group` is set.
    async make(specs, opts) {
        const app = window.app, r = window.canvasRenderer;
        const o = Object.assign({ group: true, view: 'data-flow' }, opts || {});
        this.toasts = [];
        app._toast = (msg, isError) => {
            window.__fx.toasts.push({ msg: String(msg), error: !!isError });
        };
        await this.settle();
        await fetch('/api/project/new', { method: 'POST' });
        const ids = [];
        for (const s of specs) {
            const made = await this.j('POST', '/api/layer/add', {
                name: s.name, columns: s.columns, rows: s.rows,
                cabinet_width: s.w, cabinet_height: s.h,
                offset_x: s.x || 0, offset_y: s.y || 0 });
            ids.push(made.id);
        }
        const shape = (l, s) => Object.assign(l, {
            processorType: 'novastar-armor', bitDepth: 8, frameRate: 60,
            lowLatency: false, portMappingMode: 'organized',
            flowPattern: 'custom', lastFlowPattern: 'tl-h',
            powerFlowPattern: 'custom', lastPowerFlowPattern: 'tl-h',
            powerCustomPath: true, powerOrganized: true, powerMaximize: false,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
            customPortPaths: {}, customPortIndex: 1, customPortOverrides: [],
            powerCustomPaths: {}, powerCustomIndex: 1, powerCustomOverrides: [],
            locked: false,
        }, o.group ? { group_id: 'gF' } : {}, s.props || {});
        const apply = (layers) => specs.forEach((s, i) => {
            const l = layers.find(x => x.id === ids[i]);
            if (l) shape(l, s);
        });
        const p = await this.j('GET', '/api/project');
        apply(p.layers);
        p.groups = o.group ? [{ id: 'gF', name: 'WALL', layer_ids: ids }] : [];
        await this.j('PUT', '/api/project', p);
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('custom_audit_fixes');
        apply(app.project.layers);
        const first = app.project.layers.find(l => l.id === ids[0]);
        app.currentLayer = first;
        app.selectedLayerIds = new Set(ids);
        app.lastSelectedLayerId = first.id;
        app._overrideEditing = null;
        if (app.customSelection) app.customSelection.clear();
        if (app.powerCustomSelection) app.powerCustomSelection.clear();
        r.viewMode = o.view;
        app.renderLayers();
        app.loadLayerToInputs();
        app.resetHistory('Initial State');
        if (typeof r.fitToView === 'function') r.fitToView();
        r.render();
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        return ids;
    },
    layer(id) { return window.app.project.layers.find(l => l.id === id); },
    panel(l, row, col) { return l.panels.find(p => p.row === row && p.col === col); },
    // What the port's load badge is drawn from, for run `num` of `owner`.
    badge(owner, num) {
        const app = window.app, r = window.canvasRenderer;
        const path = (owner.customPortPaths || {})[num] || [];
        const panels = app.getResolvedPathPanels(owner, path).map(h => h.panel);
        return r.getPortLoadStats(owner, panels);
    },
    sumPixels(owner, num) {
        const app = window.app;
        const path = (owner.customPortPaths || {})[num] || [];
        return app.getResolvedPathPanels(owner, path)
            .reduce((s, h) => s + app.getPanelPixelArea(h.panel), 0);
    },
    tile(kind, pattern) {
        const sel = kind === 'power'
            ? `.power-flow-pattern-btn[data-pattern="${pattern}"]`
            : `.flow-pattern-btn:not(.power-flow-pattern-btn)[data-pattern="${pattern}"]`;
        document.querySelector(sel).click();
    },
    errors() { return this.toasts.filter(t => t.error).map(t => t.msg); },
};
"""


def _run(page, body, arg=None):
    page.evaluate(HELPERS_JS)
    return page.evaluate(
        "async (arg) => { const fx = window.__fx; %s }" % body, arg)


def _tab(page, mode):
    page.locator(f'#view-tabs [data-mode="{mode}"]').click()
    page.wait_for_function(
        "(m) => window.canvasRenderer && window.canvasRenderer.viewMode === m", arg=mode)


KINDS = [('data', 'data-flow'), ('power', 'power')]

# 10 x 10 cabinets of 128 x 128 px, one screen, custom data.
WALL_10 = "[{ name: 'Wall', columns: 10, rows: 10, w: 128, h: 128, x: 0, y: 0, props: %s }]"


# ── 1. a custom port is charged the way its badge charges it ──────────────

L_SHAPE_JS = r"""
    const ids = await fx.make(%s, { group: false, view: 'data-flow' });
    const app = window.app, r = window.canvasRenderer;
    const W = fx.layer(ids[0]);
    // Row 0 left to right, then down the right-hand column.
    const clicks = [];
    for (let c = 0; c < 10; c++) clicks.push([0, c]);
    for (let row = 1; row < 10; row++) clicks.push([row, 9]);
    clicks.forEach(([row, col]) => app.addPanelToCustomPath(fx.panel(W, row, col), W));
    await fx.settle();
    const fill = app.customRunFill(W, 'data', 1);
    const stats = fx.badge(W, 1);
    r.render();
    return {
        count: (W.customPortPaths[1] || []).length,
        fill: { load: fill.load, limit: fill.limit, text: fill.text, full: fill.full,
                count: fill.count },
        badge: { load: stats.load, capacity: stats.capacity, state: stats.state,
                 shown: stats.shown },
        sum: fx.sumPixels(W, 1),
        pill: r._lastActiveBadge ? r._lastActiveBadge.pill : null,
        readout: document.getElementById('custom-fill-readout').textContent,
        errors: fx.errors(),
        cap: app.calculatePortCapacity(8, 60, W.processorType, false),
    };
"""


def test_armor_l_shape_is_refused_where_the_badge_calls_it_full(page):
    """The audit's repro. Row 0 is a 10 x 1 rectangle (10 cabinets' worth);
    each step down column 9 adds a whole row to the rectangle, so the port
    is at 40 cabinets' worth (655,360 px of 659,722) after three steps and
    the fourth is refused. Before the fix all 19 went on ("19/40") and the
    badge read 248%."""
    _tab(page, 'data-flow')
    out = _run(page, L_SHAPE_JS % (WALL_10 % "{ processorType: 'novastar-armor' }"))
    cab = 128 * 128
    assert out['cap'] == 659722, out
    assert out['count'] == 13, out
    # The badge says the port fits, and the custom figures are the badge's.
    assert out['badge']['state'] == 'ok', out
    assert out['fill']['load'] == out['badge']['load'] == 40 * cab, out
    assert out['fill']['limit'] == out['badge']['capacity'], out
    # ...and not the cabinets' own sum, which is what custom used to charge.
    assert out['sum'] == 13 * cab, out
    # The readout counts the cabinets placed against the port's capacity
    # (the pre-beta ruling, tests/test_audit_final_fixes.py), and the run is
    # not full: the holes inside its rectangle cost nothing and still fit.
    assert out['fill']['text'] == '13/40' and out['fill']['full'] is False, out
    assert out['pill'] == '13/40 on port', out
    assert '13/40 panels' in out['readout'] and '· full' not in out['readout'], out
    assert any('is full' in e for e in out['errors']), out


def test_other_processors_keep_the_plain_sum(page):
    """Brompton has no rectangle rule: the same L is 19 cabinets of pixels,
    well under its 525,000 px port, and every click lands."""
    _tab(page, 'data-flow')
    out = _run(page, L_SHAPE_JS % (WALL_10 % "{ processorType: 'brompton' }"))
    cab = 128 * 128
    assert out['count'] == 19, out
    assert out['fill']['load'] == out['badge']['load'] == out['sum'] == 19 * cab, out
    assert out['badge']['state'] == 'ok', out
    assert out['fill']['text'] == f"19/{out['fill']['count']}", out
    assert out['errors'] == [], out


def test_custom_load_matches_the_badge_on_every_processor(page):
    """The same uneven run read on every processor the app has a table for:
    the custom load and the badge's load are one number on each, the
    rectangle on Armor and the sum everywhere else."""
    _tab(page, 'data-flow')
    out = _run(page, r"""
        const ids = await fx.make(%s, { group: false, view: 'data-flow' });
        const app = window.app;
        const W = fx.layer(ids[0]);
        const path = [[0, 0], [0, 1], [0, 2], [1, 2], [2, 2], [2, 3]]
            .map(([row, col]) => ({ row, col }));
        W.customPortPaths = { 1: path };
        const rows = Object.keys(app.portCapacityTables || {}).map(type => {
            W.processorType = type;
            const stats = fx.badge(W, 1);
            return { type, custom: app.customRunFill(W, 'data', 1).load,
                     badge: stats ? stats.load : null,
                     rect: app.usesRectangleConstraint(type) };
        });
        W.customPortPaths = {};
        W.processorType = 'novastar-armor';
        return rows;
    """ % (WALL_10 % "{}"))
    cab = 128 * 128
    assert len(out) > 3, out
    for row in out:
        if row['badge'] is None:
            continue
        assert row['custom'] == row['badge'], row
        assert row['badge'] == (12 * cab if row['rect'] else 6 * cab), row


def test_armor_max_capacity_fill_never_cuts_a_port_the_badge_calls_over(page):
    """Max Capacity packs one snake and cuts mid-row - on Armor a run that
    turns the corner into a fourth row pays for the whole fourth row, so a
    12-wide block cuts after three rows (36), not at 40 cabinets."""
    _tab(page, 'data-flow')
    out = _run(page, r"""
        const ids = await fx.make([{ name: 'Wall', columns: 12, rows: 6, w: 128, h: 128,
            props: { portMappingMode: 'max-capacity' } }], { group: false, view: 'data-flow' });
        const app = window.app;
        const W = fx.layer(ids[0]);
        W.panels.forEach(p => app.customSelection.add(app.getScopedPanelKey(W.id, p)));
        app.applyPatternToSelection('tl-h');
        await fx.settle();
        const nums = Object.keys(W.customPortPaths).filter(n => W.customPortPaths[n].length);
        return nums.map(n => {
            const stats = fx.badge(W, n);
            return { n, count: W.customPortPaths[n].length, state: stats.state };
        });
    """)
    assert [r['count'] for r in out] == [36, 36], out
    assert all(r['state'] == 'ok' for r in out), out


# ── 2. a partial group fill names the screens it unwired ──────────────────

# Upper 10 x 2 over Lower 10 x 1 and Side 2 x 3 to their right, one wall.
GROUP_JS = r"""
    const ids = await fx.make([
        { name: 'Upper', columns: 10, rows: 2, w: 128, h: 128, x: 0, y: 0 },
        { name: 'Lower', columns: 10, rows: 1, w: 128, h: 128, x: 0, y: 256 },
        { name: 'Side', columns: 2, rows: 3, w: 128, h: 128, x: 1280, y: 0 },
    ], { group: true, view: arg.view });
    const app = window.app;
    const [U, L, S] = ids.map(id => fx.layer(id));
    const isPower = arg.kind === 'power';
    const key = isPower ? 'powerCustomPaths' : 'customPortPaths';
    // Run 1 starts on Upper and crosses into Lower (and, when asked, Side).
    const run = [{ row: 1, col: 0 }, { row: 1, col: 1 },
                 { row: 0, col: 1, layerId: L.id }, { row: 0, col: 0, layerId: L.id }];
    if (arg.side) run.push({ row: 1, col: 9 }, { row: 1, col: 0, layerId: S.id });
    U[key] = { 1: run };
    app.currentLayer = U;
    app.selectedLayerIds = new Set(arg.selectAll ? ids : [U.id]);
    fx.toasts = [];
    fx.tile(arg.kind, 'tl-h');
    await fx.settle();
    const wiredOn = (layer) => app.getPathScopeLayers(U).flatMap(m =>
        Object.values(m[key] || {}).flat().filter(e => e
            && app.getPathEntryLayerId(m, e) === layer.id)).length;
    return {
        lower: wiredOn(L), side: wiredOn(S),
        upper: wiredOn(U),
        toasts: fx.toasts.map(t => t.msg),
    };
"""


@pytest.mark.parametrize('kind,view', KINDS)
def test_partial_group_tile_names_the_screen_it_unwired(page, kind, view):
    _tab(page, view)
    out = _run(page, GROUP_JS, {'kind': kind, 'view': view})
    noun = 'Circuits' if kind == 'power' else 'Runs'
    # The ruling's behaviour stays: the crossing run was redone as a whole.
    assert out['lower'] == 0, out
    assert out['upper'] == 20, out
    assert (f"{noun} that crossed into Lower were redone — "
            "Lower's cabinets on them are now unwired.") in out['toasts'], out


@pytest.mark.parametrize('kind,view', KINDS)
def test_partial_group_tile_lists_every_screen_it_unwired(page, kind, view):
    _tab(page, view)
    out = _run(page, GROUP_JS, {'kind': kind, 'view': view, 'side': True})
    noun = 'Circuits' if kind == 'power' else 'Runs'
    assert out['lower'] == 0 and out['side'] == 0, out
    assert (f"{noun} that crossed into Lower and Side were redone — "
            "those screens' cabinets on them are now unwired.") in out['toasts'], out


@pytest.mark.parametrize('kind,view', KINDS)
def test_whole_group_tile_unwires_nothing_and_says_nothing(page, kind, view):
    _tab(page, view)
    out = _run(page, GROUP_JS, {'kind': kind, 'view': view, 'selectAll': True})
    assert out['lower'] == 10, out
    assert not any('crossed into' in t for t in out['toasts']), out
