"""Custom drawing caps at capacity, and a pattern fill cuts there.

The wall that asked for this (2026-09-03): 28 cabinets wide on 110 V / 15 A.
Automatic power refuses it - a full row is more than a circuit carries - so
the user goes to custom mode, selects a 14 x 6 block, presses serpentine, and
wants circuits 1..6 at 14 apiece. Before this the pattern buttons poured the
WHOLE selection into the one active circuit, and a click past the cap was
taken without a word.

Two contracts, pinned on both sides (power circuits and data ports):

* CLICK-DRAWING IS CAPPED. When the active run is full, the next cabinet is
  REFUSED with a message that names the run, the cap and the way forward
  (Tab / ]). The run does NOT advance on its own - a click that silently
  moved the cursor would land the cabinet somewhere the user did not look.
* PATTERN FILL CUTS AT CAPACITY. The selection is walked in pattern order,
  the active run fills to its cap, the next number takes over, until the
  selection is consumed. ONE undo entry. The active index ends on the last
  number filled, so the badge names what was just drawn.

The cap is the sidebar's own figure, never a second derivation: power is
watts per circuit against each cabinet's watt-equivalent (a half-tile is
derated the way calculatePowerAssignments derates it), data is pixels per
port against each cabinet's pixel area.

Run locally:
    python -m pytest tests/test_custom_capacity_cap.py -v --browser chromium
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


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


# One screen built through the real add endpoint so cabinets carry real
# geometry. 115 W cabinets on a 110 V / 15 A circuit (1,650 W) pack 14 to a
# circuit - the user's own figure. 256 px cabinets (65,536 px) on a Brompton
# port at 8-bit / 60 Hz (525,000 px) pack 8 to a port.
HELPERS_JS = r"""
window.__cap = {
    toasts: [],
    async reset(opts) {
        const app = window.app, r = window.canvasRenderer;
        const o = Object.assign({ columns: 28, rows: 6, cab: 128 }, opts || {});
        this.toasts = [];
        app._toast = (msg) => { window.__cap.toasts.push(String(msg)); };
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
                name: 'Wide', columns: o.columns, rows: o.rows,
                cabinet_width: o.cab, cabinet_height: o.cab,
                offset_x: 0, offset_y: 0,
            }),
        });
        app.project = await (await fetch('/api/project')).json();
        app.dedupeProjectLayers('custom_capacity_cap_reset');
        const l = app.project.layers.find(x => (x.type || 'screen') === 'screen');
        l.flowPattern = o.autoData ? 'tl-h' : 'custom';
        l.powerFlowPattern = o.autoPower ? 'tl-h' : 'custom';
        l.powerCustomPath = !o.autoPower;
        l.powerOrganized = true;
        l.powerMaximize = false;
        l.powerVoltage = 110;
        l.powerAmperage = 15;
        l.panelWatts = 115;
        l.processorType = 'brompton';
        l.bitDepth = 8;
        l.frameRate = 60;
        l.lowLatency = false;
        l.customPortPaths = {};
        l.customPortIndex = 1;
        l.customPortOverrides = [];
        l.powerCustomPaths = {};
        l.powerCustomIndex = 1;
        l.powerCustomOverrides = [];
        app.currentLayer = l;
        app.selectedLayerIds = new Set([l.id]);
        app._overrideEditing = null;
        app._overrideHover = null;
        if (app.customSelection) app.customSelection.clear();
        if (app.powerCustomSelection) app.powerCustomSelection.clear();
        r.viewMode = o.view || 'power';
        app.loadLayerToInputs();
        app.resetHistory('Initial State');
        r.render();
        if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
        return { id: l.id, panels: l.panels.length };
    },
    layer() { return window.app.currentLayer; },
    rect(cols, rows, cab) {
        // A hair inside the block: the marquee is inclusive at both edges.
        return { x1: 1, y1: 1, x2: cols * cab - 1, y2: rows * cab - 1 };
    },
    paths(key) {
        const l = this.layer();
        const paths = l[key] || {};
        const out = {};
        Object.keys(paths).forEach(n => {
            out[n] = (paths[n] || []).map(e => [e.row, e.col]);
        });
        return out;
    },
    hist() { return window.app.history.map(h => h.action); },
    panel(row, col) { return window.app.getPanelByRowCol(this.layer(), row, col); },
    // Row `row` becomes half-height cabinets - the shape the app's own
    // half-tile edit leaves (halfTile 'height', height halved).
    halveRow(row) {
        const l = this.layer();
        l.panels.filter(p => p.row === row).forEach(p => {
            p.halfTile = 'height';
            p.height = l.cabinet_height / 2;
        });
    },
    badge() {
        window.canvasRenderer.render();
        return window.canvasRenderer._lastActiveBadge || null;
    },
    readout(kind) {
        const el = document.getElementById(kind === 'power'
            ? 'power-custom-fill-readout' : 'custom-fill-readout');
        return el ? el.textContent : null;
    },
};
"""


def reset(page, **opts):
    state = page.evaluate("(o) => window.__cap.reset(o)", opts)
    page.wait_for_timeout(400)
    return state


def hist(page):
    return page.evaluate("() => window.__cap.hist()")


def toasts(page):
    return page.evaluate("() => window.__cap.toasts.slice()")


# ── Pattern fill cuts at capacity ─────────────────────────────────────────

def test_power_serpentine_over_a_14x6_block_fills_circuits_1_to_6_at_14_each(page):
    """The user's gesture, exactly: 28 wide, select 14 x 6, press serpentine.
    Six circuits of fourteen, snaking, one undo step, cursor on circuit 6."""
    reset(page)
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        app.selectPowerPanelsInRect(cap.layer(), cap.rect(14, 6, 128));
        const selected = app.powerCustomSelection.size;
        app.applyPowerPatternToSelection('tl-h');
        return {
            selected,
            paths: cap.paths('powerCustomPaths'),
            active: cap.layer().powerCustomIndex,
            hist: cap.hist(),
            toasts: cap.toasts.slice(),
        };
    }""")
    assert out['selected'] == 84, out['selected']
    paths = out['paths']
    assert sorted(int(k) for k in paths) == [1, 2, 3, 4, 5, 6], paths.keys()
    for n in range(1, 7):
        assert len(paths[str(n)]) == 14, (n, len(paths[str(n)]))
    # Serpentine: row 0 left to right, row 1 right to left, ...
    assert paths['1'] == [[0, c] for c in range(14)], paths['1']
    assert paths['2'] == [[1, c] for c in range(13, -1, -1)], paths['2']
    assert paths['6'] == [[5, c] for c in range(13, -1, -1)], paths['6']
    # The active index ends on the LAST number filled.
    assert out['active'] == 6, out['active']
    # One undo entry for the whole fill.
    assert out['hist'] == ['Initial State', 'Power Custom Pattern Apply'], out['hist']
    # And the status says what was filled, with the cap it was filled to.
    assert len(out['toasts']) == 1, out['toasts']
    assert out['toasts'][0].startswith('Filled circuits '), out['toasts'][0]
    assert '14 panels each at 110V/15A' in out['toasts'][0], out['toasts'][0]


def test_power_fill_is_one_undo_step_that_puts_everything_back(page):
    reset(page)
    before = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        app.selectPowerPanelsInRect(cap.layer(), cap.rect(14, 6, 128));
        app.applyPowerPatternToSelection('tl-h');
        return { n: Object.keys(cap.paths('powerCustomPaths')).length,
                 active: cap.layer().powerCustomIndex };
    }""")
    assert before == {'n': 6, 'active': 6}, before
    page.evaluate("() => window.app.undo()")
    page.wait_for_timeout(1200)
    after = page.evaluate("""() => {
        const cap = window.__cap;
        const paths = cap.paths('powerCustomPaths');
        return {
            drawn: Object.keys(paths).filter(n => paths[n].length > 0).length,
            active: cap.layer().powerCustomIndex,
        };
    }""")
    assert after == {'drawn': 0, 'active': 1}, after


def test_power_fill_counts_half_tiles_by_watt_equivalent(page):
    """A half-height row derates to 0.65 of a cabinet (getPanelLoadFactor),
    so circuit 1 carries 14 halves (1,046.5 W) plus 5 wholes (575 W) before
    a 6th whole (1,736.5 W) would cross 1,650 W. Same figures the automatic
    engine's loadOf charges."""
    reset(page)
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        cap.halveRow(0);
        app.selectPowerPanelsInRect(cap.layer(), cap.rect(14, 3, 128));
        app.applyPowerPatternToSelection('tl-h');
        const paths = cap.paths('powerCustomPaths');
        return {
            counts: Object.keys(paths).map(n => [Number(n), paths[n].length]),
            fill1: app.customRunFill(cap.layer(), 'power', 1),
            active: cap.layer().powerCustomIndex,
        };
    }""")
    assert out['counts'] == [[1, 19], [2, 14], [3, 9]], out['counts']
    assert abs(out['fill1']['load'] - 1621.5) < 1e-6, out['fill1']
    assert out['active'] == 3, out['active']


def test_data_serpentine_cuts_at_the_pixel_derived_port_cap(page):
    """The data twin: 256 px cabinets on a 525,000 px Brompton port pack 8,
    so a 12 x 2 block is ports 1, 2, 3 at 8 apiece."""
    reset(page, columns=12, rows=2, cab=256, view='data-flow')
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        app.selectPanelsInRect(cap.layer(), cap.rect(12, 2, 256));
        const selected = app.customSelection.size;
        app.applyPatternToSelection('tl-h');
        return {
            selected,
            cap: app.customRunCapacity(cap.layer(), 'data'),
            paths: cap.paths('customPortPaths'),
            active: cap.layer().customPortIndex,
            hist: cap.hist(),
            toasts: cap.toasts.slice(),
        };
    }""")
    assert out['selected'] == 24, out['selected']
    assert out['cap']['count'] == 8 and out['cap']['limit'] == 525000, out['cap']
    paths = out['paths']
    assert [len(paths[str(n)]) for n in (1, 2, 3)] == [8, 8, 8], paths
    assert paths['1'] == [[0, c] for c in range(8)], paths['1']
    assert paths['2'] == [[0, 8], [0, 9], [0, 10], [0, 11],
                          [1, 11], [1, 10], [1, 9], [1, 8]], paths['2']
    assert out['active'] == 3, out['active']
    assert out['hist'] == ['Initial State', 'Custom Pattern Apply'], out['hist']
    assert len(out['toasts']) == 1 and out['toasts'][0].startswith('Filled ports '), out['toasts']
    assert '8 panels each at 525,000 px/port' in out['toasts'][0], out['toasts'][0]


def test_a_selection_that_fits_one_run_is_written_quietly_as_before(page):
    """The old contract survives where the cap is not reached: one run, no
    toast, one history step."""
    reset(page, columns=12, rows=2, cab=256, view='data-flow')
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        app.selectPanelsInRect(cap.layer(), cap.rect(4, 2, 256));
        app.applyPatternToSelection('tl-h');
        const paths = cap.paths('customPortPaths');
        return { keys: Object.keys(paths), n: paths['1'].length,
                 active: cap.layer().customPortIndex, toasts: cap.toasts.slice() };
    }""")
    assert out == {'keys': ['1'], 'n': 8, 'active': 1, 'toasts': []}, out


def test_a_fill_overwrites_only_the_numbers_it_fills_and_says_so(page):
    """Circuit 3 had a drawing; the fill from circuit 1 runs into it and
    replaces it (named in the status), circuit 9 is left alone."""
    reset(page)
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        const l = cap.layer();
        l.powerCustomPaths[3] = [{ row: 5, col: 27 }];
        l.powerCustomPaths[9] = [{ row: 5, col: 26 }];
        app.selectPowerPanelsInRect(l, cap.rect(14, 3, 128));
        app.applyPowerPatternToSelection('tl-h');
        const paths = cap.paths('powerCustomPaths');
        return { p3: paths['3'], p9: paths['9'], toasts: cap.toasts.slice() };
    }""")
    assert out['p3'] == [[2, c] for c in range(14)], out['p3']
    assert out['p9'] == [[5, 26]], out['p9']
    assert len(out['toasts']) == 1 and 'replaced circuit ' in out['toasts'][0], out['toasts']


def test_a_cabinet_on_a_run_outside_the_fill_still_refuses_the_whole_apply(page):
    """Conflict detection keeps its all-or-nothing rule against runs the
    fill would NOT overwrite."""
    reset(page)
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        const l = cap.layer();
        l.powerCustomPaths[9] = [{ row: 0, col: 0 }];
        app.selectPowerPanelsInRect(l, cap.rect(14, 3, 128));
        app.applyPowerPatternToSelection('tl-h');
        const paths = cap.paths('powerCustomPaths');
        return { keys: Object.keys(paths).filter(n => paths[n].length > 0),
                 hist: cap.hist(), toasts: cap.toasts.slice() };
    }""")
    assert out['keys'] == ['9'], out['keys']
    assert out['hist'] == ['Initial State'], out['hist']
    assert len(out['toasts']) == 1 and out['toasts'][0].startswith('Cannot apply'), out['toasts']


# ── Click-drawing is capped ───────────────────────────────────────────────

def test_power_click_past_the_cap_is_refused_and_does_not_advance(page):
    reset(page)
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        const l = cap.layer();
        for (let c = 0; c < 14; c++) app.addPanelToCustomPowerPath(cap.panel(0, c));
        const h14 = cap.hist().length;
        const before = cap.toasts.length;
        app.addPanelToCustomPowerPath(cap.panel(0, 14));
        return {
            n: cap.paths('powerCustomPaths')['1'].length,
            active: l.powerCustomIndex,
            steps: cap.hist().length - h14,
            toasts: cap.toasts.slice(before),
            fill: app.customRunFill(l, 'power', 1),
        };
    }""")
    assert out['n'] == 14, out
    assert out['active'] == 1, out
    assert out['steps'] == 0, out
    assert len(out['toasts']) == 1, out['toasts']
    msg = out['toasts'][0]
    assert 'is full — 14 panels at 110V/15A' in msg, msg
    assert 'Step to the next circuit (Tab / ])' in msg, msg
    assert out['fill']['full'] is True and out['fill']['count'] == 14, out['fill']


def test_data_click_past_the_cap_is_refused(page):
    reset(page, columns=12, rows=2, cab=256, view='data-flow')
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        for (let c = 0; c < 8; c++) app.addPanelToCustomPath(cap.panel(0, c));
        const before = cap.toasts.length;
        app.addPanelToCustomPath(cap.panel(0, 8));
        return { n: cap.paths('customPortPaths')['1'].length,
                 active: cap.layer().customPortIndex,
                 toasts: cap.toasts.slice(before) };
    }""")
    assert out['n'] == 8 and out['active'] == 1, out
    assert len(out['toasts']) == 1, out['toasts']
    assert 'is full — 8 panels at 525,000 px/port' in out['toasts'][0], out['toasts']
    assert 'Step to the next port (Tab / ])' in out['toasts'][0], out['toasts']


def test_a_per_run_override_is_capped_by_the_same_gate(page):
    """Alt takeover shares the click path. Automatic organized rows on a
    14-wide screen put row 0 (1,610 W) on circuit 1; taken over, it is
    already full, and the first click onto row 1 is refused."""
    reset(page, columns=14, rows=3, autoPower=True)
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        const l = cap.layer();
        app.overrideRun(l, 'power', 1);
        const seeded = cap.paths('powerCustomPaths')['1'].length;
        const before = cap.toasts.length;
        app.addPanelToCustomPowerPath(cap.panel(1, 0));
        return {
            seeded,
            editing: !!app._isOverrideEditing(l, 'power'),
            n: cap.paths('powerCustomPaths')['1'].length,
            toasts: cap.toasts.slice(before),
        };
    }""")
    assert out['seeded'] == 14 and out['editing'] is True, out
    assert out['n'] == 14, out
    assert len(out['toasts']) == 1 and 'is full' in out['toasts'][0], out['toasts']


def test_no_capacity_means_no_cap(page):
    """No wattage set: the run takes whatever is drawn, exactly as before."""
    reset(page)
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        const l = cap.layer();
        l.panelWatts = 0;
        for (let c = 0; c < 20; c++) app.addPanelToCustomPowerPath(cap.panel(0, c));
        return { n: cap.paths('powerCustomPaths')['1'].length,
                 known: app.customRunCapacity(l, 'power').known,
                 toasts: cap.toasts.slice() };
    }""")
    assert out == {'n': 20, 'known': False, 'toasts': []}, out


# ── The fill is on screen while drawing ───────────────────────────────────

def test_the_badge_reads_the_fill_and_calls_the_run_full(page):
    reset(page)
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        for (let c = 0; c < 9; c++) app.addPanelToCustomPowerPath(cap.panel(0, c));
        const mid = cap.badge();
        const midReadout = cap.readout('power');
        for (let c = 9; c < 14; c++) app.addPanelToCustomPowerPath(cap.panel(0, c));
        const full = cap.badge();
        const fullReadout = cap.readout('power');
        return { mid, midReadout, full, fullReadout };
    }""")
    assert out['mid']['pill'] == '9/14 on circuit', out['mid']
    assert out['mid']['full'] is False, out['mid']
    assert out['full']['pill'] == '14/14 on circuit · full', out['full']
    assert out['full']['full'] is True, out['full']
    # The sidebar mirrors it under the custom controls.
    assert '9/14 panels' in out['midReadout'] and '(110V/15A)' in out['midReadout'], out['midReadout']
    assert '14/14 panels · full' in out['fullReadout'], out['fullReadout']


def test_the_data_badge_and_readout_mirror_the_port_cap(page):
    reset(page, columns=12, rows=2, cab=256, view='data-flow')
    out = page.evaluate("""() => {
        const app = window.app, cap = window.__cap;
        for (let c = 0; c < 8; c++) app.addPanelToCustomPath(cap.panel(0, c));
        return { badge: cap.badge(), readout: cap.readout('data') };
    }""")
    assert out['badge']['pill'] == '8/8 on port · full', out['badge']
    assert '8/8 panels · full' in out['readout'], out['readout']
    assert '525,000 px/port' in out['readout'], out['readout']


def test_the_auto_power_refusal_names_the_pattern_fill_route(page):
    """The message the user hit: it now says the custom route works."""
    reset(page, autoPower=True)
    why = page.evaluate("() => window.app._socaPlanEmptyReason(window.__cap.layer())")
    assert why and 'a full row is' in why, why
    assert 'select a narrower block and apply a pattern' in why, why
    assert 'circuits cut at capacity' in why, why
