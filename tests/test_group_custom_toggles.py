"""Custom mode on a grouped wall of two cabinet sizes.

The wall (synthetic, the shape of the owner's report): an upper screen of
20 x 4 cabinets at 192 x 384 px and a lower screen of 20 x 1 at 192 x 192 px
directly under it, grouped, NovaStar Armor at 8-bit / 60 Hz, top-left
vertical, Organized. The owner's rulings, 2026-10-16:

1. AUTO: "Only mixed sizes stay apart." A group whose cabinet sizes differ
   keeps routing per screen, and the greyed "Route <group> as one screen"
   switch says why in plain words. A same-size group keeps the switch.
2. A PATTERN TILE IN CUSTOM MODE never takes the screen out of custom mode.
   With no cabinets selected it fills the selected screen, or the selected
   group, as custom runs - and with no screen selected it does nothing.
   Data and power.
3. THE TOGGLE is idempotent: the model follows the box, a repeated event
   that changes nothing is a no-op, and a real second click is applied
   rather than dropped. Data and power. (The reversed-echo guard has its
   own module, tests/test_custom_audit_1_5.py.)
4. THE READOUT reads pixels for a run over two cabinet sizes,
   "442,368 / 659,722 px", watts for a circuit over two wattages,
   "1,660 / 4,160 W", and a cabinet count for one kind of cabinet.
5. RIGHT-CLICK on a screen or group in Data / Power toggles custom mode for
   that tab through the same path as the box, as one undo step.

Run locally:
    python -m pytest tests/test_group_custom_toggles.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

SIZES_DIFFER = 'Cabinet sizes differ - runs stay per screen. Use Custom to run across.'


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
    # the app's own first load lands before the test touches the project
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


HELPERS_JS = r"""
window.__gc = {
    toasts: [],
    async j(method, url, body) {
        const res = await fetch(url, {
            method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        return res.json();
    },
    settle(ms) { return new Promise(r => setTimeout(r, ms || 300)); },
    async fresh(opts) {
        const app = window.app, r = window.canvasRenderer;
        const o = Object.assign({ mixed: true, custom: false, view: 'data-flow',
            lowerWatts: 200 }, opts || {});
        this.toasts = [];
        app._toast = (msg) => { window.__gc.toasts.push(String(msg)); };
        await Promise.all([...(app._inflightLayerPuts || [])]);
        await Promise.all([...((app._layerPutChains && app._layerPutChains.values()) || [])]
            .map(p => p.catch(() => {})));
        await fetch('/api/project/new', { method: 'POST' });
        const add = (body) => this.j('POST', '/api/layer/add', body);
        const up = await add({ name: 'Upper', columns: 20, rows: 4,
            cabinet_width: 192, cabinet_height: 384, offset_x: 0, offset_y: 0 });
        const low = await add({ name: 'Lower', columns: 20, rows: 1,
            cabinet_width: 192, cabinet_height: o.mixed ? 192 : 384,
            offset_x: 0, offset_y: 4 * 384 });
        const ids = [up.id, low.id];
        const shape = (l) => Object.assign(l, {
            processorType: 'novastar-armor', bitDepth: 8, frameRate: 60,
            lowLatency: false, portMappingMode: 'organized',
            flowPattern: o.custom ? 'custom' : 'tl-v', lastFlowPattern: 'tl-v',
            powerFlowPattern: o.custom ? 'custom' : 'tl-v', lastPowerFlowPattern: 'tl-v',
            powerCustomPath: !!o.custom, powerOrganized: true, powerMaximize: false,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
            customPortPaths: {}, customPortIndex: 1, customPortOverrides: [],
            powerCustomPaths: {}, powerCustomIndex: 1, powerCustomOverrides: [],
            group_id: 'g2',
        });
        const p = await this.j('GET', '/api/project');
        p.layers.filter(l => ids.includes(l.id)).forEach(shape);
        p.layers.filter(l => l.id === low.id).forEach(l => { l.panelWatts = o.lowerWatts; });
        p.groups = [{ id: 'g2', name: 'WALL', layer_ids: ids }];
        await this.j('PUT', '/api/project', p);
        await this.settle(200);
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('group_custom_toggles');
        app.project.layers.filter(l => ids.includes(l.id)).forEach(shape);
        app.project.layers.filter(l => l.id === low.id).forEach(l => { l.panelWatts = o.lowerWatts; });
        const U = app.project.layers.find(l => l.id === up.id);
        app.currentLayer = U;
        app.selectedLayerIds = new Set(ids);
        app.lastSelectedLayerId = U.id;
        app._overrideEditing = null;
        // A box change left from an earlier test must not read as the
        // first half of a double-fire here (app-wiring _customToggleEcho).
        app._customToggleLast = {};
        app._customToggleClock = undefined;
        if (app.customSelection) app.customSelection.clear();
        if (app.powerCustomSelection) app.powerCustomSelection.clear();
        r.viewMode = o.view;
        app.renderLayers();
        app.loadLayerToInputs();
        app.resetHistory('Initial State');
        if (typeof r.fitToView === 'function') r.fitToView();
        r.render();
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        return { up: up.id, low: low.id };
    },
    layer(id) { return window.app.project.layers.find(l => l.id === id); },
    state(ids) {
        const app = window.app;
        const U = this.layer(ids.up), L = this.layer(ids.low);
        const shown = (id) => {
            const el = document.getElementById(id);
            return !!el && el.style.display !== 'none';
        };
        return {
            flow: [U.flowPattern, L.flowPattern],
            power: [U.powerFlowPattern, L.powerFlowPattern],
            dataBox: document.getElementById('custom-flow-toggle').checked,
            powerBox: document.getElementById('power-custom-toggle').checked,
            dataPanel: shown('custom-flow-controls'),
            powerPanel: shown('power-custom-controls'),
            historyIndex: app.historyIndex,
            action: app.history[app.historyIndex] ? app.history[app.historyIndex].action : null,
        };
    },
    // Every cabinet on the owner's runs, and how many sit on a peer.
    runs(owner, kind) {
        const paths = (kind === 'power' ? owner.powerCustomPaths : owner.customPortPaths) || {};
        const all = Object.values(paths).flat();
        return {
            cabinets: all.length,
            onPeer: all.filter(e => e.layerId !== undefined && e.layerId !== owner.id).length,
            runs: Object.keys(paths).filter(n => (paths[n] || []).length > 0).length,
        };
    },
    tile(kind, pattern) {
        const sel = kind === 'power'
            ? `.power-flow-pattern-btn[data-pattern="${pattern}"]`
            : `.flow-pattern-btn:not(.power-flow-pattern-btn)[data-pattern="${pattern}"]`;
        document.querySelector(sel).click();
    },
    // The client point of a cabinet's centre on the canvas.
    clientOf(layer, panel) {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        const off = window.app._getLayerWorkspaceOffset(layer);
        const wx = off.wx + panel.x + panel.width / 2;
        const wy = off.wy + panel.y + panel.height / 2;
        return { x: rect.left + r.panX + wx * r.zoom, y: rect.top + r.panY + wy * r.zoom };
    },
};
"""


def _run(page, body, arg=None):
    page.evaluate(HELPERS_JS)
    return page.evaluate(
        "async (arg) => { const gc = window.__gc; %s }" % body, arg)


def _tab(page, mode):
    page.locator(f'#view-tabs [data-mode="{mode}"]').click()
    page.wait_for_timeout(300)


# ── 1. auto mode: only mixed sizes stay apart ─────────────────────────────

ROUTE_ROW_JS = r"""
    const app = window.app;
    app.updatePortCapacityDisplay();
    const row = document.getElementById('route-group-as-one-row');
    const box = document.getElementById('route-group-as-one');
    const note = document.getElementById('route-group-as-one-note');
    const U = gc.layer(ids.up), L = gc.layer(ids.low);
    const maxPort = (l) => app.calculatePortAssignments(l)
        .reduce((m, x) => Math.max(m, x.port || 0), 0);
    return {
        rowShown: row.style.display !== 'none',
        enabled: !box.disabled,
        hint: row.title,
        noteShown: note.style.display !== 'none',
        note: note.textContent,
        plan: !!app.getAutoRoutePlan(U, 'data'),
        lowerServedByPeer: app.isServedByPeerRouting(L, 'data'),
        upperPorts: maxPort(U),
        lowerPorts: maxPort(L),
    };
"""


def test_mixed_size_group_routes_per_screen_and_says_why(page):
    _tab(page, 'data-flow')
    out = _run(page, "const ids = await gc.fresh({ mixed: true });" + ROUTE_ROW_JS)
    assert out['plan'] is False, out
    assert out['lowerServedByPeer'] is False, out
    # Upper: 80 cabinets of 73,728 px at 659,722 px/port -> its own ports;
    # lower: 20 of 36,864 px -> its own ports. Neither reads 0.
    assert out['upperPorts'] > 0 and out['lowerPorts'] > 0, out
    assert out['rowShown'] is True, out
    assert out['enabled'] is False, out
    assert out['noteShown'] is True, out
    assert out['note'] == SIZES_DIFFER, out
    assert out['hint'] == SIZES_DIFFER, out


def test_same_size_group_keeps_the_switch(page):
    _tab(page, 'data-flow')
    out = _run(page, "const ids = await gc.fresh({ mixed: false });" + ROUTE_ROW_JS)
    assert out['plan'] is True, out
    assert out['lowerServedByPeer'] is True, out
    assert out['rowShown'] is True, out
    assert out['enabled'] is True, out
    assert out['noteShown'] is False, out
    assert out['note'] == '', out
    assert 'cables on its own' in out['hint'], out


# ── 2. a pattern tile in custom mode with no cabinets selected ────────────

@pytest.mark.parametrize('kind,view', [('data', 'data-flow'), ('power', 'power')])
def test_tile_with_nothing_selected_does_nothing(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await gc.fresh({ custom: true, view: arg.view });
        const app = window.app;
        app.selectedLayerIds = new Set();
        const before = gc.state(ids);
        gc.tile(arg.kind, 'tl-h');
        await gc.settle(200);
        const U = gc.layer(ids.up);
        return { before, after: gc.state(ids), runs: gc.runs(U, arg.kind) };
    """, {'kind': kind, 'view': view})
    after = out['after']
    assert after['flow'] == ['custom', 'custom'], out
    assert after['power'] == ['custom', 'custom'], out
    assert after['historyIndex'] == out['before']['historyIndex'], out
    assert out['runs']['cabinets'] == 0, out
    assert after['dataBox'] is True and after['powerBox'] is True, out


@pytest.mark.parametrize('kind,view', [('data', 'data-flow'), ('power', 'power')])
def test_tile_with_the_group_selected_fills_the_whole_group(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await gc.fresh({ custom: true, view: arg.view });
        const app = window.app;
        // Owner: the lower screen, so the readout has to count across sizes.
        app.currentLayer = gc.layer(ids.low);
        app.selectedLayerIds = new Set([ids.up, ids.low]);
        app.loadLayerToInputs();
        gc.tile(arg.kind, 'tl-v');
        await gc.settle(200);
        const L = gc.layer(ids.low);
        return { after: gc.state(ids), runs: gc.runs(L, arg.kind),
                 toasts: gc.toasts.slice(),
                 cap: app.calculatePortCapacity(8, 60, 'novastar-armor', false) };
    """, {'kind': kind, 'view': view})
    after = out['after']
    assert after['flow'] == ['custom', 'custom'], out
    assert after['power'] == ['custom', 'custom'], out
    assert after['dataBox'] is True and after['powerBox'] is True, out
    assert out['runs']['cabinets'] == 100, out
    assert out['runs']['onPeer'] == 80, out
    assert out['runs']['runs'] > 1, out
    if kind == 'data':
        # A selection of two cabinet sizes names the pixel cap the cut used.
        assert any(f"up to {out['cap']:,} px each" in t for t in out['toasts']), out
        assert after['action'] == 'Custom Pattern Apply', out
    else:
        # Both members draw 200 W: one wattage keeps the cabinet count.
        assert any('up to 20 panels each at 208V/20A' in t for t in out['toasts']), out
        assert after['action'] == 'Power Custom Pattern Apply', out


def test_power_fill_over_two_wattages_names_the_watts(page):
    """A group whose members draw different watts: the fill toast names the
    circuit's watt cap the cut used, not a cabinet count."""
    _tab(page, 'power')
    out = _run(page, r"""
        const ids = await gc.fresh({ custom: true, view: 'power', lowerWatts: 115 });
        const app = window.app;
        app.currentLayer = gc.layer(ids.low);
        app.selectedLayerIds = new Set([ids.up, ids.low]);
        app.loadLayerToInputs();
        gc.tile('power', 'tl-v');
        await gc.settle(200);
        return { runs: gc.runs(gc.layer(ids.low), 'power'), toasts: gc.toasts.slice() };
    """)
    assert out['runs']['cabinets'] == 100, out
    assert any('up to 4,160 W each' in t for t in out['toasts']), out
    assert not any('panels each' in t for t in out['toasts']), out


@pytest.mark.parametrize('kind,view', [('data', 'data-flow'), ('power', 'power')])
def test_tile_with_one_screen_selected_fills_that_screen(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await gc.fresh({ custom: true, view: arg.view });
        const app = window.app;
        app.selectedLayerIds = new Set([ids.up]);
        gc.tile(arg.kind, 'tl-v');
        await gc.settle(200);
        const U = gc.layer(ids.up);
        return { after: gc.state(ids), runs: gc.runs(U, arg.kind) };
    """, {'kind': kind, 'view': view})
    assert out['after']['flow'] == ['custom', 'custom'], out
    assert out['after']['power'] == ['custom', 'custom'], out
    assert out['runs']['cabinets'] == 80, out
    assert out['runs']['onPeer'] == 0, out


# ── 3. the toggle stays with the model ────────────────────────────────────

@pytest.mark.parametrize('kind,view', [('data', 'data-flow'), ('power', 'power')])
def test_toggle_double_click_stays_in_sync(page, kind, view):
    _tab(page, view)
    box_id = 'power-custom-toggle' if kind == 'power' else 'custom-flow-toggle'
    _run(page, "window.__gcIds = await gc.fresh({ custom: false, view: arg.view });",
         {'view': view})
    # Two real clicks, back to back, each with its own pointer events: on,
    # then off. The old 600 ms guard dropped the second and left the box
    # unticked over a custom wall; the echo guard must let both through.
    page.click('#' + box_id)
    page.click('#' + box_id)
    out = _run(page, r"""
        const ids = window.__gcIds;
        // Every save of the two clicks lands before the next phase, so a
        // late answer from the server cannot be read as this phase's state
        // on a slow runner.
        await window.app._layerSavesSettled();
        const box = document.getElementById(arg.box);
        const key = arg.kind === 'power' ? 'power' : 'flow';
        const twice = gc.state(ids);
        // One click that fires change twice with the SAME state: the
        // second is a no-op.
        const start = window.app.historyIndex;
        box.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
        box.checked = true;
        box.dispatchEvent(new Event('change'));
        box.dispatchEvent(new Event('change'));
        await window.app._layerSavesSettled();
        const doubled = gc.state(ids);
        return { twice, doubled, start, key,
                 boxTwice: twice[arg.kind === 'power' ? 'powerBox' : 'dataBox'],
                 boxDoubled: doubled[arg.kind === 'power' ? 'powerBox' : 'dataBox'] };
    """, {'kind': kind, 'view': view, 'box': box_id})
    key = out['key']
    assert out['twice'][key] == ['tl-v', 'tl-v'], out
    assert out['boxTwice'] is False, out
    assert out['doubled'][key] == ['custom', 'custom'], out
    assert out['boxDoubled'] is True, out
    assert out['doubled']['historyIndex'] == out['start'] + 1, out
    panel = 'powerPanel' if kind == 'power' else 'dataPanel'
    assert out['doubled'][panel] is True, out


# ── 4. the readout on a run over two cabinet sizes ────────────────────────

def test_mixed_run_reads_pixels_and_one_size_reads_cabinets(page):
    _tab(page, 'data-flow')
    out = _run(page, r"""
        const ids = await gc.fresh({ custom: true, view: 'data-flow' });
        const app = window.app, r = window.canvasRenderer;
        const L = gc.layer(ids.low);
        app.currentLayer = L;
        app.selectedLayerIds = new Set([ids.low]);
        const read = (path) => {
            L.customPortPaths = { 1: path };
            L.customPortIndex = 1;
            app.updateCustomFlowUI();
            r.render();
            return {
                pill: r._lastActiveBadge ? r._lastActiveBadge.pill : null,
                line: document.getElementById('custom-fill-readout').textContent,
            };
        };
        const own = [0, 1, 2, 3].map(c => ({ row: 0, col: c }));
        const peer = [0, 1, 2, 3, 4, 5].map(c => ({ row: 3, col: c, layerId: ids.up }));
        // The four upper cabinets straight above the lower four: a
        // rectangle, so the Armor port pays exactly the cabinets' own
        // pixels. (An uneven run pays for the rectangle round it, Armor's
        // reserved-rectangle rule - tests/test_custom_audit_fixes.py.)
        const mixed = read(own.concat(peer.slice(0, 4)));
        const lowerOnly = read(own);
        const upperOnly = read(peer.slice(0, 3));
        // A pending marquee of the other size turns a one-size run's
        // readout to pixels too - it is drawn onto this run next.
        L.customPortPaths = { 1: own };
        app.customSelection.add(app.getScopedPanelKey(ids.up, gc.layer(ids.up).panels[0]));
        app.updateCustomFlowUI();
        r.render();
        const withSelection = r._lastActiveBadge ? r._lastActiveBadge.pill : null;
        app.customSelection.clear();
        L.customPortPaths = {};
        return { mixed, lowerOnly, upperOnly, withSelection,
                 cap: app.calculatePortCapacity(8, 60, 'novastar-armor', false) };
    """)
    cap = out['cap']
    load = 4 * 192 * 192 + 4 * 192 * 384
    assert out['mixed']['pill'] == f"{load:,} / {cap:,} px on port", out
    assert out['mixed']['line'].endswith(f": {load:,} / {cap:,} px"), out
    assert out['lowerOnly']['pill'] == f"4/{cap // (192 * 192)} on port", out
    assert out['upperOnly']['pill'] == f"3/{cap // (192 * 384)} on port", out
    assert out['withSelection'] == f"{4 * 192 * 192:,} / {cap:,} px on port", out


# ── 5. right-click a screen or group for custom mode ──────────────────────

# A cabinet on the upper screen's top row: the lower screen sits at the
# bottom of the fitted view, under the hardware dock.
MENU_OPEN_JS = r"""
    const U = gc.layer(ids.up);
    const pt = gc.clientOf(U, U.panels[5]);
    const under = document.elementFromPoint(pt.x, pt.y);
    pt.onCanvas = under === window.canvasRenderer.canvas;
    return pt;
"""

MENU_READ_JS = r"""() => {
    const item = document.querySelector('#context-menu [data-action="custom-mode-toggle"]');
    const menu = document.getElementById('context-menu');
    return { open: menu.style.display === 'block',
             shown: item.style.display !== 'none',
             label: item.textContent, title: item.title };
}"""


@pytest.mark.parametrize('kind,view,noun', [
    ('data', 'data-flow', 'runs'), ('power', 'power', 'circuits')])
def test_right_click_toggles_custom_mode_for_the_group(page, kind, view, noun):
    _tab(page, view)
    pt = _run(page, r"""
        const ids = await gc.fresh({ custom: false, view: arg.view });
        window.__gcIds = ids;
        // Only the lower screen selected: the right-click lands on the upper.
        window.app.selectLayer(gc.layer(ids.low));
        window.canvasRenderer.render();
    """ + MENU_OPEN_JS, {'view': view})
    assert pt['onCanvas'], pt
    page.mouse.click(pt['x'], pt['y'], button='right')
    page.wait_for_timeout(150)
    menu_off = page.evaluate(MENU_READ_JS)
    page.locator('#context-menu [data-action="custom-mode-toggle"]').click()
    page.wait_for_timeout(300)
    on = _run(page, "return gc.state(window.__gcIds);")
    page.mouse.click(pt['x'], pt['y'], button='right')
    page.wait_for_timeout(150)
    menu_on = page.evaluate(MENU_READ_JS)
    page.keyboard.press('Escape')
    page.evaluate("() => window.app.hideContextMenu()")
    undone = _run(page, r"""
        window.app.undo();
        await gc.settle(400);
        return gc.state(window.__gcIds);
    """)

    assert menu_off['open'] and menu_off['shown'], menu_off
    assert menu_off['label'] == f'Custom {noun}: Off', menu_off
    assert 'WALL' in menu_off['title'], menu_off
    key = 'power' if kind == 'power' else 'flow'
    box = 'powerBox' if kind == 'power' else 'dataBox'
    panel = 'powerPanel' if kind == 'power' else 'dataPanel'
    # Both members, the box and the panel - one undo step.
    assert on[key] == ['custom', 'custom'], on
    assert on[box] is True, on
    assert on[panel] is True, on
    assert on['historyIndex'] == 1, on
    assert on['action'] == ('Power Custom Mode Toggle' if kind == 'power'
                            else 'Custom Mode Toggle'), on
    assert menu_on['label'] == f'Custom {noun}: On', menu_on
    assert undone[key] == ['tl-v', 'tl-v'], undone
    assert undone[box] is False, undone


def test_right_click_offers_no_custom_item_on_other_tabs(page):
    _tab(page, 'pixel-map')
    pt = _run(page, r"""
        const ids = await gc.fresh({ custom: false, view: 'pixel-map' });
    """ + MENU_OPEN_JS)
    assert pt['onCanvas'], pt
    page.mouse.click(pt['x'], pt['y'], button='right')
    page.wait_for_timeout(150)
    menu = page.evaluate(MENU_READ_JS)
    page.evaluate("() => window.app.hideContextMenu()")
    assert menu['open'], menu
    assert menu['shown'] is False, menu


def test_mixed_watt_circuit_reads_watts_and_one_wattage_reads_cabinets(page):
    """Power twin of the pixel readout: a circuit over members that draw
    different watts reads watts against the circuit's cap (V x A), the
    figures the cut weighs; one wattage reads a count in its own cabinets."""
    _tab(page, 'power')
    out = _run(page, r"""
        const ids = await gc.fresh({ custom: true, view: 'power', lowerWatts: 115 });
        const app = window.app, r = window.canvasRenderer;
        const L = gc.layer(ids.low);
        app.currentLayer = L;
        app.selectedLayerIds = new Set([ids.low]);
        const read = (path) => {
            L.powerCustomPaths = { 1: path };
            L.powerCustomIndex = 1;
            app.updateCustomPowerUI();
            r.render();
            return {
                pill: r._lastActiveBadge ? r._lastActiveBadge.pill : null,
                line: document.getElementById('power-custom-fill-readout').textContent,
            };
        };
        const own = [0, 1, 2, 3].map(c => ({ row: 0, col: c }));
        const peer = [0, 1, 2, 3, 4, 5].map(c => ({ row: 3, col: c, layerId: ids.up }));
        const mixed = read(own.concat(peer));
        const lowerOnly = read(own);
        const upperOnly = read(peer.slice(0, 3));
        L.powerCustomPaths = { 1: own };
        app.powerCustomSelection.add(app.getScopedPanelKey(ids.up, gc.layer(ids.up).panels[0]));
        app.updateCustomPowerUI();
        r.render();
        const withSelection = r._lastActiveBadge ? r._lastActiveBadge.pill : null;
        app.powerCustomSelection.clear();
        L.powerCustomPaths = {};
        return { mixed, lowerOnly, upperOnly, withSelection };
    """)
    limit = 208 * 20
    load = 4 * 115 + 6 * 200
    assert out['mixed']['pill'] == f"{load:,} / {limit:,} W on circuit", out
    assert out['mixed']['line'].endswith(f": {load:,} / {limit:,} W"), out
    assert out['lowerOnly']['pill'] == f"4/{limit // 115} on circuit", out
    assert out['upperOnly']['pill'] == f"3/{limit // 200} on circuit", out
    assert out['withSelection'] == f"{4 * 115:,} / {limit:,} W on circuit", out
