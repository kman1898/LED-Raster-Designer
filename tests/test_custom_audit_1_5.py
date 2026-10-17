"""Custom mode after the 1.5 audit.

Each test below fails on 1.5.0 and passes with the fix it names. The wall
for the group tests is the shape of the owner's report (synthetic): an
upper screen of 20 x 4 cabinets at 192 x 384 px over a lower screen of
20 x 1 at 192 x 192 px, grouped, NovaStar Armor at 8-bit / 60 Hz.

1. A second pattern tile on a selected group REFILLS the group from run 1
   (tl-h then tl-v used to be refused: "97 panels already wired to other
   ports"), and the cabinet selection the tile borrowed is always handed
   back - on a refusal too.
2. A tile never takes a screen out of custom mode, whichever screen is
   shown (the owner's ruling, 2026-10-16).
3. Turning custom off rewrites only the screens that were custom; the
   right-click item acts only on the clicked screen and its group, and its
   title names them.
4. The mac double-fire: a reversed `change` with no pointer or key press in
   between is ignored and the box re-synced; two real clicks both apply.
5. Locked screens stay unchanged and an error names them (the owner's
   ruling, 2026-10-16) - stepping the active port or circuit included.
6. Custom data capacity is the automatic one: the Low Latency (1 - Y/H)
   derate and the 5G 128 px narrow-port penalty.
7. (a) a tile with no layer at all leaves the highlight alone; (b) the
   "sizes differ" note reads the gate's own members; (c) the taken-over
   runs refusal speaks pixels on a run over two cabinet sizes.

Run locally:
    python -m pytest tests/test_custom_audit_1_5.py -v --browser chromium
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
    # the app's own first load lands before the test touches the project
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(2000)
    yield pg
    context.close()


HELPERS_JS = r"""
window.__ca = {
    toasts: [],
    async j(method, url, body) {
        const res = await fetch(url, {
            method, headers: {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        return res.json();
    },
    // Waits on the saves themselves, never on the clock: every layer save
    // made so far has landed and been read back.
    async settle() {
        await window.app._layerSavesSettled();
        await new Promise(r => setTimeout(r, 0));
    },
    // Screens from specs: [{ name, columns, rows, w, h, x, y, custom,
    // pattern, props }], grouped as one wall when `group` is set.
    async make(specs, opts) {
        const app = window.app, r = window.canvasRenderer;
        const o = Object.assign({ group: true, view: 'data-flow' }, opts || {});
        this.toasts = [];
        app._toast = (msg, isError) => {
            window.__ca.toasts.push({ msg: String(msg), error: !!isError });
        };
        await Promise.all([...(app._inflightLayerPuts || [])]);
        await Promise.all([...((app._layerPutChains && app._layerPutChains.values()) || [])]
            .map(p => p.catch(() => {})));
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
            flowPattern: s.custom ? 'custom' : (s.pattern || 'tl-v'),
            lastFlowPattern: s.last || 'tl-v',
            powerFlowPattern: s.custom ? 'custom' : (s.pattern || 'tl-v'),
            lastPowerFlowPattern: s.last || 'tl-v',
            powerCustomPath: !!s.custom, powerOrganized: true, powerMaximize: false,
            powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
            customPortPaths: {}, customPortIndex: 1, customPortOverrides: [],
            powerCustomPaths: {}, powerCustomIndex: 1, powerCustomOverrides: [],
            locked: false,
        }, o.group ? { group_id: 'gA' } : {}, s.props || {});
        const apply = (layers) => specs.forEach((s, i) => {
            const l = layers.find(x => x.id === ids[i]);
            if (l) shape(l, s);
        });
        const p = await this.j('GET', '/api/project');
        apply(p.layers);
        p.groups = o.group ? [{ id: 'gA', name: 'WALL', layer_ids: ids }] : [];
        await this.j('PUT', '/api/project', p);
        await this.settle(200);
        app.project = await this.j('GET', '/api/project');
        app.dedupeProjectLayers('custom_audit');
        apply(app.project.layers);
        const first = app.project.layers.find(l => l.id === ids[0]);
        app.currentLayer = first;
        app.selectedLayerIds = new Set(ids);
        app.lastSelectedLayerId = first.id;
        app._overrideEditing = null;
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
        return ids;
    },
    wall(opts) {
        return this.make([
            { name: 'Upper', columns: 20, rows: 4, w: 192, h: 384, x: 0, y: 0,
              custom: !!(opts && opts.custom) },
            { name: 'Lower', columns: 20, rows: 1, w: 192, h: 192, x: 0, y: 4 * 384,
              custom: !!(opts && opts.custom) },
        ], Object.assign({ group: true }, opts || {}));
    },
    layer(id) { return window.app.project.layers.find(l => l.id === id); },
    paths(l, kind) { return (kind === 'power' ? l.powerCustomPaths : l.customPortPaths) || {}; },
    index(l, kind) { return kind === 'power' ? l.powerCustomIndex : l.customPortIndex; },
    sel(kind) { const a = window.app; return kind === 'power' ? a.powerCustomSelection : a.customSelection; },
    runs(owner, kind) {
        const paths = this.paths(owner, kind);
        const nums = Object.keys(paths).filter(n => (paths[n] || []).length > 0);
        const all = nums.flatMap(n => paths[n]);
        return {
            cabinets: all.length, runs: nums.length,
            onPeer: all.filter(e => e.layerId !== undefined && e.layerId !== owner.id).length,
            first: nums.length ? Math.min(...nums.map(Number)) : null,
            last: nums.length ? Math.max(...nums.map(Number)) : null,
        };
    },
    tile(kind, pattern) {
        const sel = kind === 'power'
            ? `.power-flow-pattern-btn[data-pattern="${pattern}"]`
            : `.flow-pattern-btn:not(.power-flow-pattern-btn)[data-pattern="${pattern}"]`;
        document.querySelector(sel).click();
    },
    activeTile(kind) {
        const sel = kind === 'power' ? '.power-flow-pattern-btn.active'
            : '.flow-pattern-btn:not(.power-flow-pattern-btn).active';
        const b = document.querySelector(sel);
        return b ? b.getAttribute('data-pattern') : null;
    },
    errors() { return this.toasts.filter(t => t.error).map(t => t.msg); },
};
"""


def _run(page, body, arg=None):
    page.evaluate(HELPERS_JS)
    return page.evaluate(
        "async (arg) => { const ca = window.__ca; %s }" % body, arg)


def _tab(page, mode):
    page.locator(f'#view-tabs [data-mode="{mode}"]').click()
    page.wait_for_timeout(300)


KINDS = [('data', 'data-flow'), ('power', 'power')]


# ── 1. a second tile refills the group ─────────────────────────────────────

@pytest.mark.parametrize('kind,view', KINDS)
def test_second_tile_on_the_group_refills_from_run_one(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.wall({ custom: true, view: arg.view });
        const app = window.app;
        let U = ca.layer(ids[0]);
        ca.tile(arg.kind, 'tl-h');
        await ca.settle(200);
        U = ca.layer(ids[0]);
        const first = { runs: ca.runs(U, arg.kind), index: ca.index(U, arg.kind),
                        sel: ca.sel(arg.kind).size, steps: app.historyIndex };
        ca.tile(arg.kind, 'tl-v');
        await ca.settle(200);
        U = ca.layer(ids[0]);
        return { first,
                 second: { runs: ca.runs(U, arg.kind), index: ca.index(U, arg.kind),
                           sel: ca.sel(arg.kind).size, steps: app.historyIndex,
                           firstRun: ca.paths(U, arg.kind)['1'] },
                 errors: ca.errors() };
    """, {'kind': kind, 'view': view})
    first, second = out['first'], out['second']
    assert first['runs']['cabinets'] == 100, out
    assert out['errors'] == [], out
    assert second['runs']['cabinets'] == 100, out
    assert second['runs']['first'] == 1, out
    assert second['index'] == second['runs']['last'], out
    assert second['sel'] == 0, out
    assert second['steps'] == first['steps'] + 1, 'refill must be one undo step: %r' % out
    # tl-v: run 1 starts down the first column - Upper's four cabinets, then
    # Lower's one.
    col0 = [e for e in second['firstRun'] if e['col'] == 0]
    assert len(col0) == 5, out


@pytest.mark.parametrize('kind,view', KINDS)
def test_a_refused_refill_hands_the_selection_back(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.wall({ custom: true, view: arg.view });
        const app = window.app;
        const realCap = app.calculatePortCapacity;
        if (arg.kind === 'power') {
            app.project.layers.forEach(l => { l.panelWatts = 5000; });
        } else {
            app.calculatePortCapacity = () => 1000;
        }
        try {
            ca.tile(arg.kind, 'tl-h');
            await ca.settle(200);
        } finally {
            app.calculatePortCapacity = realCap;
        }
        return { runs: ca.runs(ca.layer(ids[0]), arg.kind), sel: ca.sel(arg.kind).size,
                 errors: ca.errors() };
    """, {'kind': kind, 'view': view})
    assert out['runs']['cabinets'] == 0, out
    assert any(e.startswith('Cannot apply:') for e in out['errors']), out
    assert out['sel'] == 0, 'the borrowed cabinet keys were left selected: %r' % out


# ── 2. a tile never takes a screen out of custom mode ──────────────────────

@pytest.mark.parametrize('kind,view', KINDS)
def test_tile_on_an_auto_screen_leaves_a_selected_custom_screen_custom(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.make([
            { name: 'U', columns: 4, rows: 2, w: 128, h: 128, x: 0, y: 0 },
            { name: 'L', columns: 4, rows: 2, w: 128, h: 128, x: 0, y: 600, custom: true },
        ], { group: false, view: arg.view });
        const app = window.app;
        app.currentLayer = ca.layer(ids[0]);
        app.selectedLayerIds = new Set(ids);
        app.loadLayerToInputs();
        ca.tile(arg.kind, 'bl-h');
        await ca.settle(200);
        const f = arg.kind === 'power' ? 'powerFlowPattern' : 'flowPattern';
        return { u: ca.layer(ids[0])[f], l: ca.layer(ids[1])[f], active: ca.activeTile(arg.kind) };
    """, {'kind': kind, 'view': view})
    assert out['u'] == 'bl-h', out
    assert out['l'] == 'custom', out
    assert out['active'] == 'bl-h', out


# ── 3. custom off only where it was on; the right-click item's reach ──────

@pytest.mark.parametrize('kind,view', KINDS)
def test_custom_off_leaves_a_screen_that_was_never_custom(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.make([
            { name: 'U', columns: 4, rows: 2, w: 128, h: 128, x: 0, y: 0, custom: true, last: 'tr-h' },
            { name: 'L', columns: 4, rows: 2, w: 128, h: 128, x: 0, y: 600, pattern: 'bl-v', last: 'br-h' },
        ], { group: false, view: arg.view });
        const app = window.app;
        if (arg.kind === 'power') app.toggleCustomPowerMode(false);
        else app.toggleCustomFlowMode(false);
        await ca.settle(200);
        const f = arg.kind === 'power' ? 'powerFlowPattern' : 'flowPattern';
        return { u: ca.layer(ids[0])[f], l: ca.layer(ids[1])[f] };
    """, {'kind': kind, 'view': view})
    assert out['u'] == 'tr-h', out
    assert out['l'] == 'bl-v', 'a screen that was never custom was rewritten: %r' % out


@pytest.mark.parametrize('kind,view,noun', [('data', 'data-flow', 'runs'),
                                            ('power', 'power', 'circuits')])
def test_right_click_item_acts_only_on_the_clicked_screen_and_names_it(page, kind, view, noun):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.make([
            { name: 'U', columns: 4, rows: 2, w: 128, h: 128, x: 0, y: 0 },
            { name: 'L', columns: 4, rows: 2, w: 128, h: 128, x: 0, y: 600 },
        ], { group: false, view: arg.view });
        const app = window.app;
        // Both selected; the shown screen U is the one the item is for.
        app.currentLayer = ca.layer(ids[0]);
        app.selectedLayerIds = new Set(ids);
        const armed = app._prepareCustomModeMenu(-1, -1);
        app._customModeMenuAction = armed;
        document.dispatchEvent(new PointerEvent('pointerdown'));
        app.runCustomModeMenu();
        await ca.settle(200);
        const isOn = arg.kind === 'power' ? (l => app.isCustomPower(l)) : (l => app.isCustomFlow(l));
        return { title: armed.title, u: isOn(ca.layer(ids[0])), l: isOn(ca.layer(ids[1])),
                 selected: [...app.selectedLayerIds] , ids };
    """, {'kind': kind, 'view': view})
    assert out['title'] == f'Turn custom {noun} on for U', out
    assert out['u'] is True, out
    assert out['l'] is False, 'the item changed a screen its title never named: %r' % out
    assert out['selected'] == [out['ids'][0]], out


def test_right_click_title_names_the_group_and_its_screens(page):
    _tab(page, 'data-flow')
    out = _run(page, r"""
        await ca.wall({ view: 'data-flow' });
        return window.app._prepareCustomModeMenu(-1, -1).title;
    """)
    assert out == 'Turn custom runs on for WALL (Upper and Lower)', out


# ── 4. the mac double-fire ────────────────────────────────────────────────

@pytest.mark.parametrize('kind,view', KINDS)
def test_a_reversed_echo_of_one_click_is_ignored_and_the_box_resynced(page, kind, view):
    """Driven with a held clock and explicit events - nothing here depends
    on how fast the runner is."""
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.wall({ view: arg.view });
        const app = window.app;
        const box = document.getElementById(arg.kind === 'power' ? 'power-custom-toggle' : 'custom-flow-toggle');
        const isOn = arg.kind === 'power' ? (l => app.isCustomPower(l)) : (l => app.isCustomFlow(l));
        const read = () => ({ on: ids.map(id => isOn(ca.layer(id))), box: box.checked });
        let now = 1000;
        app._customToggleClock = () => now;
        try {
            // One click: its pointer event, then change (on) - and the
            // WKWebView echo 370 ms later, change again with the state
            // reversed and no pointer or key press in between.
            box.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
            box.checked = true;
            box.dispatchEvent(new Event('change'));
            now += 370;
            box.checked = false;
            box.dispatchEvent(new Event('change'));
            await app._layerSavesSettled();
            const echo = read();
            // The same reversed change past the window is the user's.
            now += 700;
            box.checked = false;
            box.dispatchEvent(new Event('change'));
            await app._layerSavesSettled();
            const late = read();
            // And inside the window WITH a key press in between, too.
            box.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }));
            box.checked = true;
            box.dispatchEvent(new Event('change'));
            now += 10;
            box.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }));
            box.checked = false;
            box.dispatchEvent(new Event('change'));
            await app._layerSavesSettled();
            const keyed = read();
            return { echo, late, keyed };
        } finally {
            app._customToggleClock = undefined;
        }
    """, {'kind': kind, 'view': view})
    assert out['echo'] == {'on': [True, True], 'box': True}, \
        'the echo flipped the mode, or the box shows the opposite of the model: %r' % out
    assert out['late'] == {'on': [False, False], 'box': False}, out
    assert out['keyed'] == {'on': [False, False], 'box': False}, out


@pytest.mark.parametrize('kind,view', KINDS)
def test_two_real_clicks_both_apply(page, kind, view):
    _tab(page, view)
    box = '#power-custom-toggle' if kind == 'power' else '#custom-flow-toggle'
    _run(page, "window.__caIds = await ca.wall({ view: arg.view });", {'view': view})
    page.click(box)
    page.click(box)
    out = _run(page, r"""
        const app = window.app;
        await app._layerSavesSettled();
        const isOn = arg.kind === 'power' ? (l => app.isCustomPower(l)) : (l => app.isCustomFlow(l));
        return { on: window.__caIds.map(id => isOn(ca.layer(id))),
                 box: document.querySelector(arg.box).checked, steps: app.historyIndex };
    """, {'kind': kind, 'box': box})
    assert out['on'] == [False, False], out
    assert out['box'] is False, out
    assert out['steps'] == 2, out


@pytest.mark.parametrize('kind,view', KINDS)
def test_two_clicks_a_held_clock_apart_both_apply(page, kind, view):
    """The same two clicks with the clock held still between them: each
    brings its own pointer event, so neither is read as an echo however
    close together they land."""
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.wall({ view: arg.view });
        const app = window.app;
        const box = document.getElementById(arg.kind === 'power' ? 'power-custom-toggle' : 'custom-flow-toggle');
        const isOn = arg.kind === 'power' ? (l => app.isCustomPower(l)) : (l => app.isCustomFlow(l));
        app._customToggleClock = () => 5000;
        try {
            box.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
            box.click();
            box.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
            box.click();
            await app._layerSavesSettled();
        } finally {
            app._customToggleClock = undefined;
        }
        return { on: ids.map(id => isOn(ca.layer(id))), box: box.checked, steps: app.historyIndex };
    """, {'kind': kind, 'view': view})
    assert out == {'on': [False, False], 'box': False, 'steps': 2}, out


# ── 5. locked screens stay unchanged and say why ──────────────────────────

LOCKED = 'Lower is locked - unlock it to change it.'


@pytest.mark.parametrize('kind,view', KINDS)
def test_group_tile_leaves_a_locked_member_and_names_it(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.wall({ custom: true, view: arg.view });
        ca.layer(ids[1]).locked = true;
        ca.tile(arg.kind, 'tl-v');
        await ca.settle(200);
        return { runs: ca.runs(ca.layer(ids[0]), arg.kind), errors: ca.errors() };
    """, {'kind': kind, 'view': view})
    assert out['runs']['cabinets'] == 80, out
    assert out['runs']['onPeer'] == 0, out
    assert out['errors'] == [LOCKED], out


@pytest.mark.parametrize('kind,view', KINDS)
def test_tile_on_a_locked_owner_changes_nothing(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.wall({ custom: true, view: arg.view });
        ca.layer(ids[0]).locked = true;
        const steps = window.app.historyIndex;
        ca.tile(arg.kind, 'tl-v');
        await ca.settle(200);
        return { runs: ca.runs(ca.layer(ids[0]), arg.kind), errors: ca.errors(),
                 steps, after: window.app.historyIndex, sel: ca.sel(arg.kind).size };
    """, {'kind': kind, 'view': view})
    assert out['runs']['cabinets'] == 0, out
    assert out['errors'] == ['Upper is locked - unlock it to change it.'], out
    assert out['after'] == out['steps'], out
    assert out['sel'] == 0, out


@pytest.mark.parametrize('kind,view', KINDS)
def test_custom_toggle_leaves_a_locked_member_and_names_it(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.wall({ view: arg.view });
        const app = window.app;
        ca.layer(ids[1]).locked = true;
        if (arg.kind === 'power') app.toggleCustomPowerMode(true);
        else app.toggleCustomFlowMode(true);
        await ca.settle(200);
        const f = arg.kind === 'power' ? 'powerFlowPattern' : 'flowPattern';
        return { u: ca.layer(ids[0])[f], l: ca.layer(ids[1])[f], errors: ca.errors() };
    """, {'kind': kind, 'view': view})
    assert out['u'] == 'custom', out
    assert out['l'] == 'tl-v', out
    assert out['errors'] == [LOCKED], out


@pytest.mark.parametrize('kind,view', KINDS)
def test_auto_tile_leaves_a_locked_screen_and_names_it(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.make([
            { name: 'U', columns: 4, rows: 2, w: 128, h: 128, x: 0, y: 0 },
            { name: 'Lower', columns: 4, rows: 2, w: 128, h: 128, x: 0, y: 600 },
        ], { group: false, view: arg.view });
        ca.layer(ids[1]).locked = true;
        ca.tile(arg.kind, 'br-v');
        await ca.settle(200);
        const f = arg.kind === 'power' ? 'powerFlowPattern' : 'flowPattern';
        return { u: ca.layer(ids[0])[f], l: ca.layer(ids[1])[f], errors: ca.errors() };
    """, {'kind': kind, 'view': view})
    assert out['u'] == 'br-v', out
    assert out['l'] == 'tl-v', out
    assert out['errors'] == [LOCKED], out


@pytest.mark.parametrize('kind,view', KINDS)
def test_clicking_a_locked_cabinet_onto_a_run_is_refused(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.wall({ custom: true, view: arg.view });
        const app = window.app;
        const L = ca.layer(ids[1]);
        L.locked = true;
        if (arg.kind === 'power') app.addPanelToCustomPowerPath(L.panels[0], L);
        else app.addPanelToCustomPath(L.panels[0], L);
        return { runs: ca.runs(ca.layer(ids[0]), arg.kind), errors: ca.errors() };
    """, {'kind': kind, 'view': view})
    assert out['runs']['cabinets'] == 0, out
    assert out['errors'] == [LOCKED], out


@pytest.mark.parametrize('kind,view', KINDS)
def test_taking_over_a_run_on_a_locked_screen_is_refused(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        const ids = await ca.make([
            { name: 'Lower', columns: 4, rows: 2, w: 128, h: 128, x: 0, y: 0 },
        ], { group: false, view: arg.view });
        const app = window.app;
        const L = ca.layer(ids[0]);
        L.locked = true;
        app.overrideRun(L, arg.kind, 1);
        return { overrides: app.getOverrideNums(L, arg.kind), errors: ca.errors() };
    """, {'kind': kind, 'view': view})
    assert out['overrides'] == [], out
    assert out['errors'] == [LOCKED], out


# Stepping the active port or circuit is a change too (the owner's ruling,
# 2026-10-16: "Block it too"). Every way to step - the call the shortcuts and
# menu items share, Tab and ] on the canvas, the Next button, a number typed
# in the active box - leaves a locked screen's index where it was, takes no
# undo step and names the screen.
STEP_JS = r"""
    const app = window.app;
    const ids = await ca.wall({ custom: true, view: arg.view });
    const U = ca.layer(ids[0]);
    U.locked = arg.locked;
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    const steps = app.historyIndex;
    const key = (code) => document.dispatchEvent(
        new KeyboardEvent('keydown', { code, key: code === 'Tab' ? 'Tab' : ']', bubbles: true }));
    const nextId = arg.kind === 'power' ? 'power-custom-next' : 'custom-next-port';
    const boxId = arg.kind === 'power' ? 'power-custom-active' : 'custom-active-port-input';
    const seen = [];
    const record = () => seen.push(ca.index(ca.layer(ids[0]), arg.kind));
    if (arg.way === 'call') { app.stepCustomPort(1); record(); }
    if (arg.way === 'tab') { key('Tab'); record(); }
    if (arg.way === 'bracket') { key('BracketRight'); record(); }
    if (arg.way === 'button') { document.getElementById(nextId).click(); record(); }
    if (arg.way === 'box') {
        const box = document.getElementById(boxId);
        box.value = '3';
        box.dispatchEvent(new Event('change', { bubbles: true }));
        record();
        seen.push(Number(box.value));
    }
    await ca.settle(200);
    return { seen, errors: ca.errors(), steps, after: app.historyIndex };
"""

STEP_WAYS = ['call', 'tab', 'bracket', 'button', 'box']


@pytest.mark.parametrize('way', STEP_WAYS)
@pytest.mark.parametrize('kind,view', KINDS)
def test_stepping_the_active_run_on_a_locked_screen_is_refused(page, kind, view, way):
    _tab(page, view)
    out = _run(page, STEP_JS, {'kind': kind, 'view': view, 'way': way, 'locked': True})
    assert all(v == 1 for v in out['seen']), out
    assert out['errors'] == ['Upper is locked - unlock it to change it.'], out
    assert out['after'] == out['steps'], out


@pytest.mark.parametrize('way', STEP_WAYS)
@pytest.mark.parametrize('kind,view', KINDS)
def test_stepping_the_active_run_on_an_unlocked_screen_still_steps(page, kind, view, way):
    _tab(page, view)
    out = _run(page, STEP_JS, {'kind': kind, 'view': view, 'way': way, 'locked': False})
    assert out['seen'][0] == (3 if way == 'box' else 2), out
    assert out['errors'] == [], out


# ── 6. custom data capacity is the automatic one ──────────────────────────

CAPACITY_JS = r"""
    const app = window.app, r = window.canvasRenderer;
    app.selectedLayerIds = new Set([ids[0]]);
    ca.tile('data', arg.pattern);
    await ca.settle(200);
    const U = ca.layer(ids[0]);
    const paths = U.customPortPaths || {};
    const runs = Object.keys(paths).filter(n => paths[n].length).map(n => {
        const panels = app.getResolvedPathPanels(U, paths[n]).map(h => h.panel);
        const stats = r.getPortLoadStats(U, panels);
        const load = panels.reduce((s, p) => s + app.getPanelPixelArea(p), 0);
        return { n, count: panels.length, load, over: stats.state === 'over',
                 badge: r.getPortCapacityForPanels(U, panels),
                 custom: app.customRunCapacity(U, 'data', panels).limit,
                 fill: app.customRunFill(U, 'data', Number(n)).limit };
    });
    return { runs, base: app.calculatePortCapacity(8, 60, U.processorType, !!U.lowLatency),
             errors: ca.errors() };
"""


def test_custom_runs_carry_the_low_latency_derate(page):
    _tab(page, 'data-flow')
    out = _run(page, r"""
        const H = window.app.getLayerCanvasHeight(window.app.currentLayer) || 1080;
        const ids = await ca.make([
            { name: 'U', columns: 10, rows: 4, w: 128, h: 128, x: 0, y: Math.round(H / 2),
              custom: true, props: { lowLatency: true } },
        ], { group: false, view: 'data-flow' });
    """ + CAPACITY_JS, {'pattern': 'tl-h'})
    runs = out['runs']
    assert len(runs) > 1, out
    for run in runs:
        assert run['over'] is False, 'a custom run is over its derated capacity: %r' % out
        assert run['custom'] == run['badge'], out
        assert run['fill'] == run['badge'], out
        assert run['badge'] < out['base'], out


def test_custom_runs_carry_the_5g_narrow_port_penalty(page):
    _tab(page, 'data-flow')
    out = _run(page, r"""
        const ids = await ca.make([
            { name: 'U', columns: 1, rows: 100, w: 64, h: 512, x: 0, y: 0,
              custom: true, props: { processorType: 'novastar-5g' } },
        ], { group: false, view: 'data-flow' });
    """ + CAPACITY_JS, {'pattern': 'tl-v'})
    runs = out['runs']
    assert sum(r['count'] for r in runs) == 100, out
    for run in runs:
        assert run['over'] is False, 'a custom run is over its 5G capacity: %r' % out
        assert run['custom'] == run['badge'], out
        assert run['fill'] == run['badge'], out
    # 64 px wide: each port loses (128 - 64) x its height, so a port carries
    # 45 of these cabinets, not the 90 the table figure alone would allow.
    assert [r['count'] for r in runs] == [45, 45, 10], out


def test_a_click_past_the_derated_cap_is_refused(page):
    _tab(page, 'data-flow')
    out = _run(page, r"""
        const ids = await ca.make([
            { name: 'U', columns: 1, rows: 100, w: 64, h: 512, x: 0, y: 0,
              custom: true, props: { processorType: 'novastar-5g' } },
        ], { group: false, view: 'data-flow' });
        const app = window.app, U = ca.layer(ids[0]);
        U.customPortPaths = { 1: U.panels.slice(0, 45).map(p => ({ row: p.row, col: p.col })) };
        U.customPortIndex = 1;
        app.addPanelToCustomPath(U.panels[45], U);
        return { count: U.customPortPaths[1].length, errors: ca.errors() };
    """)
    assert out['count'] == 45, out
    assert any('is full' in e for e in out['errors']), out


# ── 7. the low ones ──────────────────────────────────────────────────────

@pytest.mark.parametrize('kind,view', KINDS)
def test_tile_with_no_layer_at_all_keeps_its_highlight(page, kind, view):
    _tab(page, view)
    out = _run(page, r"""
        await ca.wall({ view: arg.view });
        const app = window.app;
        const before = ca.activeTile(arg.kind);
        app.currentLayer = null;
        app.selectedLayerIds = new Set();
        ca.tile(arg.kind, 'br-h');
        await ca.settle(100);
        return { before, after: ca.activeTile(arg.kind) };
    """, {'kind': kind, 'view': view})
    assert out['before'] == 'tl-v', out
    assert out['after'] == 'tl-v', out


def test_sizes_differ_note_reads_only_the_gates_members(page):
    """Two members of different cabinet sizes on two different show
    canvases: the gate never compares them (one show canvas each), so its
    reason is not "sizes differ" and the note must not say it is."""
    _tab(page, 'data-flow')
    out = _run(page, r"""
        const ids = await ca.wall({ view: 'data-flow' });
        const app = window.app;
        ca.layer(ids[1]).show_canvas_id = 'elsewhere';
        const g = app.getGroupOfLayer(ca.layer(ids[0]));
        return { can: app._groupCanRouteDataAsOne(g), differ: app._groupCabinetSizesDiffer(g) };
    """)
    assert out['can'] is False, out
    assert out['differ'] is False, out


def test_taken_over_runs_refusal_speaks_pixels_on_a_mixed_run(page):
    _tab(page, 'data-flow')
    out = _run(page, r"""
        const ids = await ca.wall({ view: 'data-flow' });
        const app = window.app;
        const U = ca.layer(ids[0]), L = ca.layer(ids[1]);
        app.currentLayer = U;
        app.overrideRun(U, 'data', 1);
        await ca.settle(200);
        ca.toasts = [];
        // Every cabinet of both sizes: far more than the one taken-over port.
        [U, L].forEach(l => l.panels.forEach(p => app.customSelection.add(app.getScopedPanelKey(l.id, p))));
        app.applyPatternToSelection('tl-h');
        const errors = ca.errors();
        app.customSelection.clear();
        app.endOverrideEdit();
        return { errors };
    """)
    assert len(out['errors']) == 1, out
    msg = out['errors'][0]
    assert 'taken-over ports' in msg, out
    assert 'px a port' in msg, out
    assert 'panels at' not in msg, out
