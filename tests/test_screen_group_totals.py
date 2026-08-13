"""Screen groups (v0.11.0) - combined totals across a group's members.

Step 1 gave groups a data model. This is the part that makes a group worth
having: a wall built from 1m JP5 cabinets AND 0.5m standard cabinets has to be
two layers (the per-layer grid is uniform), and today every total - cabinets,
pixels, weight, watts, amps, ports, circuits - reads per layer.

The roll-up lives in the client (app-screen-info.js: getGroupTotals), because
that is where the per-layer maths it reuses already lives - getPanelLoadFactor,
calculatePowerAssignments, calculatePortAssignments. So these are Playwright
tests, driving the real app in a real browser.

They run against SYNTHETIC projects: window.app.project is swapped for a hand
built one inside a single page.evaluate and restored in a finally, so nothing
leaks into the session-shared page. The one exception is the regression guard
at the bottom, which deliberately uses the app's own live layer.

Run locally:
    python -m pytest tests/test_screen_group_totals.py -v --browser chromium
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


# Shared session fixtures (one Playwright driver + one live server) live in
# conftest.py: browser_name, e2e_server, pw_browser.

@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)  # socket connect + app init
    pg.evaluate(HELPERS_JS)
    return pg


# A layer builder and a project swapper, installed on the page once. `screen`
# produces the same shape create_layer produces server-side, with a full grid
# of panels; callers override only the fields the test is about.
HELPERS_JS = """
window.__gt = {
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'S', type: 'screen', visible: true,
            columns: 2, rows: 2,
            cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0,
            panel_weight: 20, weight_unit: 'kg',
            panelWatts: 200, powerVoltage: 208, powerAmperage: 20,
            processorType: 'brompton', bitDepth: 8, frameRate: 60,
            lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-h', powerOrganized: false, powerMaximize: false,
            group_id: 'g1',
        }, opts || {});
        const panels = [];
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    row: r, col: c,
                    x: o.offset_x + c * o.cabinet_width,
                    y: o.offset_y + r * o.cabinet_height,
                    width: o.cabinet_width, height: o.cabinet_height,
                    hidden: false, blank: false, halfTile: 'none',
                });
            }
        }
        o.panels = panels;
        return o;
    },
    withProject(layers, groups, fn) {
        const saved = window.app.project;
        window.app.project = { layers: layers, groups: groups };
        try { return fn(); } finally { window.app.project = saved; }
    },
    totals(layers, group) {
        return this.withProject(layers, [group], () => window.app.getGroupTotals(group.id));
    },
    group(layers, id) {
        return { id: id || 'g1', name: 'Wall', layer_ids: layers.map(l => l.id) };
    },
};
"""


def _totals(page, build_js):
    """Run `build_js` (returns [layers, group]) and roll the group up."""
    return page.evaluate("""() => {
        const gt = window.__gt;
        const [layers, group] = (%s)(gt);
        return gt.totals(layers, group);
    }""" % build_js)


# ── The mixed wall this feature exists for ────────────────────────────────

MIXED_WALL_JS = """(gt) => {
    const jp5 = gt.screen({
        id: 1, name: 'JP5', columns: 20, rows: 9,
        cabinet_width: 128, cabinet_height: 128,
        panel_weight: 20, panelWatts: 300,
    });
    const half = gt.screen({
        id: 2, name: 'Half', columns: 40, rows: 2,
        cabinet_width: 64, cabinet_height: 64,
        panel_weight: 6, panelWatts: 90,
        offset_y: 1152,
    });
    return [[jp5, half], gt.group([jp5, half])];
}"""


def test_mixed_wall_cabinets_and_pixels(page):
    """20x9 of 1m JP5 (128x128 px) above 40x2 of 0.5m (64x64 px).

    Cabinets: 20 x 9 = 180  +  40 x 2 = 80          -> 260
              (a JP5 is ONE cabinet, and so is a 0.5m panel)
    Pixels:   180 x (128 x 128) = 180 x 16,384 = 2,949,120
            +  80 x (64  x 64)  =  80 x  4,096 =   327,680
                                                 -----------
                                                 3,276,800
    """
    t = _totals(page, MIXED_WALL_JS)
    assert t['memberCount'] == 2
    assert t['cabinets'] == 260
    assert t['pixels'] == 3276800
    assert t['equivalentPanels'] == 260  # every cabinet is full size
    assert [m['cabinets'] for m in t['members']] == [180, 80]
    assert [m['pixels'] for m in t['members']] == [2949120, 327680]


def test_mixed_wall_weight_uses_each_members_own_cabinet_weight(page):
    """The trap this feature exists to close: the two members weigh a very
    different amount per cabinet, so one member's figure cannot stand in.

    Weight: 180 x 20 kg = 3,600 kg
          +  80 x  6 kg =   480 kg
                          ---------
                          4,080 kg   -> 4,080 x 2.20462 = 8,994.85 lb

    Reading either member's 20 kg or 6 kg across all 260 cabinets would give
    5,200 kg or 1,560 kg. Neither is the wall.
    """
    t = _totals(page, MIXED_WALL_JS)
    assert t['weightKg'] == pytest.approx(4080.0)
    assert t['weightLb'] == pytest.approx(8994.8496, abs=1e-3)
    assert [m['weightKg'] for m in t['members']] == pytest.approx([3600.0, 480.0])
    assert t['weightKg'] != pytest.approx(260 * 20.0), 'one weight used for all'


def test_mixed_wall_watts_and_amps(page):
    """Watts: 180 x 300 W = 54,000 W
             + 80 x  90 W =  7,200 W
                             --------
                             61,200 W

    Both members are on 208 V, so the group has one honest voltage.
      1-phase: I = P / V          = 61,200 / 208           = 294.2308 A
      3-phase: I = P / (V x 1.73) = 61,200 / (208 x 1.73)
                                  = 61,200 / 359.84        = 170.0756 A
    """
    t = _totals(page, MIXED_WALL_JS)
    assert t['watts'] == pytest.approx(61200.0)
    assert [m['watts'] for m in t['members']] == pytest.approx([54000.0, 7200.0])
    assert t['voltage'] == 208
    assert t['voltageMismatch'] is False
    assert t['amps1ph'] == pytest.approx(294.230769, abs=1e-5)
    assert t['amps3ph'] == pytest.approx(170.075589, abs=1e-5)
    # The 3-phase divisor is the 1.73 one, not sqrt(3) rounded elsewhere.
    assert t['amps3ph'] == pytest.approx(t['amps1ph'] / 1.73, abs=1e-9)


def test_mixed_wall_circuits(page):
    """Circuits are packed per member, then summed.

    A circuit holds 208 V x 20 A = 4,160 W.
      JP5  @ 300 W: 13 cabinets = 3,900 W (a 14th would be 4,200 W, over)
                    180 cabinets -> 13 full circuits of 13 = 169, then 11 left
                                 -> 14 circuits
      Half @  90 W: 46 cabinets = 4,140 W (a 47th would be 4,230 W, over)
                     80 cabinets -> 46, then 34 left -> 2 circuits
                                                        ----
                                                        16 circuits
    """
    t = _totals(page, MIXED_WALL_JS)
    assert [m['circuits'] for m in t['members']] == [14, 2]
    assert t['circuits'] == 16
    assert t['powerError'] is None


def test_mixed_wall_ports(page):
    """Ports are assigned per member, then summed. Brompton, 8-bit, 60 Hz is
    525,000 px a port, and Organized mapping fills whole rows.

      JP5  row = 20 x 16,384 = 327,680 px; two rows = 655,360 px, over
           -> one row a port -> 9 ports
      Half row = 40 x  4,096 = 163,840 px; both rows = 327,680 px, fits
           -> 1 port
                                                       --------
                                                       10 ports
    """
    t = _totals(page, MIXED_WALL_JS)
    assert [m['ports'] for m in t['members']] == [9, 1]
    assert t['portsPrimary'] == 10
    assert t['portsBackup'] == 10, 'every primary port has a return'


# ── Half / quarter cabinets keep their area-derated share ─────────────────

def test_a_quarter_size_cabinet_contributes_its_derated_share(page):
    """getPanelLoadFactor derates by area (x1.3, capped at 1). A cabinet at a
    quarter of the full pixel area is 0.25 x 1.3 = 0.325 of a load, not 1.

    Grid of 4 full 128x128 cabinets, one of them replaced by a 64x64:
      equivalentPanels = 3 + 0.325 = 3.325
      watts            = 3.325 x 200 W = 665 W
      weight           = 3.325 x 20 kg =  66.5 kg
      cabinets         = 4 (it is still one cabinet you have to hang)
      pixels           = 3 x 16,384 + 4,096 = 53,248
    """
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1, columns: 2, rows: 2 });
        a.panels[3].width = 64;
        a.panels[3].height = 64;
        const b = gt.screen({ id: 2, columns: 1, rows: 1, offset_y: 512 });
        return [[a, b], gt.group([a, b])];
    }""")
    member = t['members'][0]
    assert member['equivalentPanels'] == pytest.approx(3.325)
    assert member['cabinets'] == 4, 'a part cabinet is still a cabinet'
    assert member['pixels'] == 53248
    assert member['watts'] == pytest.approx(665.0)
    assert member['weightKg'] == pytest.approx(66.5)
    # ...and it lands in the group total rather than being rounded to a whole.
    assert t['equivalentPanels'] == pytest.approx(4.325)
    assert t['cabinets'] == 5


# ── Voltage: reported per member, never blended ───────────────────────────

def test_members_on_different_voltages_are_flagged_not_averaged(page):
    """110 V and 208 V members. 100 A at 110 V and 100 A at 208 V are not the
    same load, so there is no honest combined amps figure - the group says so
    and hands back the per-member ones."""
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1, columns: 2, rows: 1, powerVoltage: 110, panelWatts: 200 });
        const b = gt.screen({ id: 2, columns: 2, rows: 1, powerVoltage: 208, panelWatts: 200, offset_y: 256 });
        return [[a, b], gt.group([a, b])];
    }""")
    assert t['voltageMismatch'] is True
    assert t['voltages'] == [110, 208]
    assert t['voltage'] is None
    assert t['amps1ph'] is None, 'a blended amps figure was published'
    assert t['amps3ph'] is None
    # Watts still add up - watts are watts whatever the supply.
    assert t['watts'] == pytest.approx(800.0)
    # 400 W each: 400/110 = 3.6364 A, 400/208 = 1.9231 A.
    assert [m['amps1ph'] for m in t['members']] == pytest.approx([3.636364, 1.923077], abs=1e-5)
    assert [m['amps3ph'] for m in t['members']] == pytest.approx(
        [400 / (110 * 1.73), 400 / (208 * 1.73)], abs=1e-9)


def test_matching_voltages_are_not_flagged(page):
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1, columns: 2, rows: 1, powerVoltage: 208 });
        const b = gt.screen({ id: 2, columns: 2, rows: 1, powerVoltage: 208, offset_y: 256 });
        return [[a, b], gt.group([a, b])];
    }""")
    assert t['voltageMismatch'] is False
    assert t['voltages'] == [208]
    assert t['voltage'] == 208
    assert t['amps1ph'] == pytest.approx(t['watts'] / 208)


# ── Ports and circuits are the members' own requirements, summed ──────────

def test_ports_and_circuits_are_the_sum_of_the_members_own_requirements(page):
    """Automatic assignment walks one uniform grid, so it stays per member.
    Proven against the app's own per-layer answers rather than a constant."""
    result = page.evaluate("""() => {
        const gt = window.__gt;
        const a = gt.screen({ id: 1, columns: 20, rows: 9, panelWatts: 300 });
        const b = gt.screen({ id: 2, columns: 40, rows: 2, cabinet_width: 64,
                             cabinet_height: 64, panelWatts: 90, offset_y: 1152 });
        const layers = [a, b];
        const group = gt.group(layers);
        return gt.withProject(layers, [group], () => {
            const totals = window.app.getGroupTotals(group.id);
            const perLayer = layers.map(l => ({
                ports: window.app.getLayerPortsRequired(l),
                circuits: (window.app.calculatePowerAssignments(l).circuits || []).length,
            }));
            return { totals, perLayer };
        });
    }""")
    per_layer = result['perLayer']
    totals = result['totals']
    assert totals['portsPrimary'] == sum(p['ports'] for p in per_layer)
    assert totals['circuits'] == sum(p['circuits'] for p in per_layer)
    assert [m['ports'] for m in totals['members']] == [p['ports'] for p in per_layer]
    assert [m['circuits'] for m in totals['members']] == [p['circuits'] for p in per_layer]


# ── Members that must not contribute ──────────────────────────────────────

def test_non_screen_layers_in_a_group_are_skipped(page):
    """An image or text layer has no cabinets, no watts and no ports. It can
    only reach a group by accident, and it must not zero-poison the totals."""
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1, columns: 2, rows: 1 });
        const b = gt.screen({ id: 2, columns: 2, rows: 1, offset_y: 256 });
        const img = { id: 3, type: 'image', name: 'Logo', visible: true, group_id: 'g1' };
        const txt = { id: 4, type: 'text', name: 'Note', visible: true, group_id: 'g1' };
        return [[a, img, b, txt], gt.group([a, img, b, txt])];
    }""")
    assert t['memberCount'] == 2
    assert t['nonScreenCount'] == 2
    assert t['cabinets'] == 4
    assert [m['id'] for m in t['members']] == [1, 2]


def test_a_hidden_member_is_left_out_and_counted(page):
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1, columns: 2, rows: 1 });
        const b = gt.screen({ id: 2, columns: 2, rows: 1, offset_y: 256, visible: false });
        return [[a, b], gt.group([a, b])];
    }""")
    assert t['memberCount'] == 1
    assert t['hiddenCount'] == 1
    assert t['cabinets'] == 2
    assert t['watts'] == pytest.approx(400.0)


def test_a_group_whose_members_are_all_hidden(page):
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1, columns: 2, rows: 1, visible: false });
        const b = gt.screen({ id: 2, columns: 2, rows: 1, offset_y: 256, visible: false });
        return [[a, b], gt.group([a, b])];
    }""")
    assert t['memberCount'] == 0
    assert t['hiddenCount'] == 2
    assert (t['cabinets'], t['pixels'], t['watts'], t['weightKg']) == (0, 0, 0, 0)
    assert (t['portsPrimary'], t['circuits']) == (0, 0)
    assert t['voltage'] is None and t['voltageMismatch'] is False
    assert t['amps1ph'] == 0 and t['amps3ph'] == 0, 'no members is 0 A, not a mismatch'


def test_blank_panels_are_not_cabinets(page):
    """A blanked panel is a hole in the wall: nothing hangs there, so it has no
    weight and draws nothing. Same rule getPowerCounts and the canvas weight
    label already use."""
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1, columns: 2, rows: 2 });
        a.panels[0].blank = true;
        a.panels[1].hidden = true;
        const b = gt.screen({ id: 2, columns: 1, rows: 1, offset_y: 512 });
        return [[a, b], gt.group([a, b])];
    }""")
    assert t['members'][0]['cabinets'] == 2
    assert t['members'][0]['weightKg'] == pytest.approx(40.0)
    assert t['cabinets'] == 3


# ── Degenerate groups ─────────────────────────────────────────────────────

def test_an_empty_group_totals_to_zero(page):
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1 });
        return [[a], { id: 'g1', name: 'Empty', layer_ids: [] }];
    }""")
    assert t['groupId'] == 'g1'
    assert t['memberCount'] == 0
    assert (t['cabinets'], t['pixels'], t['watts'], t['circuits']) == (0, 0, 0, 0)
    assert t['members'] == []


def test_a_single_member_group_reports_that_member(page):
    """The server refuses to build one, but an in-flight selection or a
    hand-edited file can produce one and it must not throw."""
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1, columns: 4, rows: 3, panelWatts: 200, panel_weight: 20 });
        return [[a], gt.group([a])];
    }""")
    assert t['memberCount'] == 1
    assert t['cabinets'] == 12
    assert t['watts'] == pytest.approx(2400.0)
    assert t['weightKg'] == pytest.approx(240.0)
    assert t['amps1ph'] == pytest.approx(2400.0 / 208)


def test_a_group_naming_layers_that_do_not_exist(page):
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1, columns: 2, rows: 1 });
        return [[a], { id: 'g1', name: 'Stale', layer_ids: [1, 99, 1] }];
    }""")
    assert t['memberCount'] == 1, 'a missing id, or a repeated one, added a member'
    assert t['cabinets'] == 2


def test_a_missing_group_does_not_throw(page):
    result = page.evaluate("""() => {
        const out = {};
        [null, undefined, 'nope'].forEach((g, i) => {
            const t = window.app.getGroupTotals(g);
            out[i] = [t.memberCount, t.cabinets, t.watts, t.groupId];
        });
        return out;
    }""")
    assert list(result.values()) == [[0, 0, 0, None]] * 3


def test_weight_unit_lb_converts_to_kg(page):
    """Members can be configured in lb; the group is one figure, in kg.
    120 lb / 2.20462 = 54.4311 kg a cabinet, x 2 cabinets = 108.862 kg."""
    t = _totals(page, """(gt) => {
        const a = gt.screen({ id: 1, columns: 2, rows: 1, panel_weight: 120, weight_unit: 'lb' });
        const b = gt.screen({ id: 2, columns: 2, rows: 1, panel_weight: 10, offset_y: 256 });
        return [[a, b], gt.group([a, b])];
    }""")
    assert t['members'][0]['weightKg'] == pytest.approx(2 * 120 / 2.20462, abs=1e-6)
    assert t['weightKg'] == pytest.approx(2 * 120 / 2.20462 + 20.0, abs=1e-6)


# ── Regression guard: the per-layer path must not have moved ──────────────

def test_an_ungrouped_layers_own_totals_are_untouched(page):
    """The important one. getGroupTotals is purely additive - it reads the
    per-layer helpers, it does not change them - so a layer that is in no group
    must display exactly what it displayed before groups existed.

    Captured against the app's OWN live layer: the Ports Required, Circuits
    Required and total amps readouts plus the cached fields the canvas labels
    read, before and after a roll-up runs over that same layer.
    """
    result = page.evaluate("""() => {
        const app = window.app;
        const layer = app.project.layers.find(l => (l.type || 'screen') === 'screen');
        const savedCurrent = app.currentLayer;
        const read = () => {
            app.currentLayer = layer;
            app.updatePortCapacityDisplay();
            app.updatePowerCapacityDisplay();
            const txt = (id) => {
                const el = document.getElementById(id);
                return el ? el.textContent : null;
            };
            return {
                dom: {
                    ports: txt('ports-required'),
                    capacity: txt('port-capacity'),
                    panelsPerPort: txt('panels-per-port'),
                    wattsPerCircuit: txt('power-watts-per-circuit'),
                    panelsPerCircuit: txt('power-panels-per-circuit'),
                    circuits: txt('power-circuits-required'),
                    amps1: txt('power-total-amps-1ph'),
                    amps3: txt('power-total-amps-3ph'),
                },
                cached: {
                    amps1: layer._powerTotalAmps1,
                    amps3: layer._powerTotalAmps3,
                    circuits: layer._powerCircuitsRequired,
                    ports: layer._portsRequired,
                },
            };
        };
        try {
            const before = read();
            // Roll that very layer up as if it were in a group...
            const totals = app.getGroupTotals({
                id: 'gRegression', name: 'Guard', layer_ids: [layer.id],
            });
            const after = read();
            return { before, after, totals, layerId: layer.id,
                     grouped: !!layer.group_id };
        } finally {
            app.currentLayer = savedCurrent;
            app.updatePortCapacityDisplay();
            app.updatePowerCapacityDisplay();
        }
    }""")
    assert result['grouped'] is False, 'the guard layer was in a group'
    assert result['after']['dom'] == result['before']['dom'], (
        'a group roll-up moved the per-layer readouts')
    assert result['after']['cached'] == result['before']['cached'], (
        'a group roll-up moved the per-layer cached figures')
    # ...and the roll-up agrees with the per-layer figures it reused, so the
    # group path and the layer path cannot drift apart either.
    cached = result['before']['cached']
    totals = result['totals']
    assert totals['amps1ph'] == pytest.approx(cached['amps1'])
    assert totals['amps3ph'] == pytest.approx(cached['amps3'])
    assert totals['circuits'] == cached['circuits']
    assert totals['portsPrimary'] == cached['ports']


def test_a_member_with_no_visible_key_still_counts(page):
    """A layer that simply has no ``visible`` key is VISIBLE, not hidden.

    Every other reader agrees on this: the Python side is
    ``layer.get('visible', True)`` (app.py:1335, :1559, :1699), and the layer
    list and canvas both test ``visible === false``. The roll-up originally
    used ``!layer.visible``, copied from the project-wide power roll-up in
    app-presets.js, which had the same latent bug. That form silently drops
    the screen's cabinets, weight and watts from the total - a wall quietly
    reporting a fraction of its real load, which is the worst possible way for
    this to be wrong.
    """
    js = """
        (() => {
            const mk = (id, cols, rows, cab, weight, watts) => {
                const L = {id, type: 'screen', name: 'M' + id, group_id: 'g1',
                    columns: cols, rows: rows,
                    cabinet_width: cab, cabinet_height: cab,
                    panel_weight: weight, panelWatts: watts, weight_unit: 'kg',
                    powerVoltage: 208, powerAmperage: 20,
                    processorType: 'brompton', bitDepth: 8, frameRate: 60,
                    flowPattern: 'tl-h', offset_x: 0, offset_y: 0,
                    powerOrganized: true, portMappingMode: 'organized'};
                L.panels = [];
                for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++)
                    L.panels.push({id: r * cols + c + 1, number: r * cols + c + 1,
                        row: r, col: c, x: c * cab, y: r * cab,
                        width: cab, height: cab,
                        hidden: false, blank: false, halfTile: 'none'});
                return L;   // deliberately NO `visible` key
            };
            const saved = window.app.project;
            try {
                window.app.project = {
                    layers: [mk(1, 2, 2, 128, 20, 300), mk(2, 2, 2, 64, 6, 90)],
                    groups: [{id: 'g1', name: 'Wall', layer_ids: [1, 2]}]
                };
                return window.app.getGroupTotals('g1');
            } finally { window.app.project = saved; }
        })()
    """
    t = page.evaluate(js)
    assert t['memberCount'] == 2, 'a member with no `visible` key was skipped'
    assert t['hiddenCount'] == 0
    assert t['cabinets'] == 8                      # 4 + 4
    assert t['weightKg'] == pytest.approx(4 * 20 + 4 * 6)   # 104, not 0 and not 4*20
    assert t['watts'] == pytest.approx(4 * 300 + 4 * 90)    # 1560


def test_an_explicitly_hidden_member_is_excluded(page):
    """`visible: false` still means hidden - the fix must not make everything visible."""
    js = """
        (() => {
            const mk = (id, vis) => {
                const L = {id, type: 'screen', name: 'M' + id, group_id: 'g1',
                    columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 128,
                    panel_weight: 20, panelWatts: 300, weight_unit: 'kg',
                    powerVoltage: 208, powerAmperage: 20,
                    processorType: 'brompton', bitDepth: 8, frameRate: 60,
                    flowPattern: 'tl-h', offset_x: 0, offset_y: 0,
                    powerOrganized: true, portMappingMode: 'organized'};
                if (vis !== undefined) L.visible = vis;
                L.panels = [];
                for (let r = 0; r < 2; r++) for (let c = 0; c < 2; c++)
                    L.panels.push({id: r * 2 + c + 1, number: r * 2 + c + 1,
                        row: r, col: c, x: c * 128, y: r * 128,
                        width: 128, height: 128,
                        hidden: false, blank: false, halfTile: 'none'});
                return L;
            };
            const saved = window.app.project;
            try {
                window.app.project = {
                    layers: [mk(1, undefined), mk(2, false)],
                    groups: [{id: 'g1', name: 'Wall', layer_ids: [1, 2]}]
                };
                return window.app.getGroupTotals('g1');
            } finally { window.app.project = saved; }
        })()
    """
    t = page.evaluate(js)
    assert t['memberCount'] == 1
    assert t['hiddenCount'] == 1
    assert t['cabinets'] == 4


# ── A peer fed by a neighbour's crossing port must not also count its own ──
#
# v0.11.0: getLayerPortsRequired guarded its whole custom branch on
# `layer.customPortPaths` being present. A member in custom flow that had never
# had its custom state initialised - a project saved before the key existed, or
# a peer that inherited the group's shared flowPattern without
# ensureCustomFlowState running on it - fell through to the AUTOMATIC count.
# On a wall where the neighbour's port already feeds every one of its cabinets
# that is a phantom extra port in the roll-up: the wall reads 2 Mains when one
# cable does it. Same shape for circuits.

_FED_BY_PEER_JS = """(gt) => {
    const owner = gt.screen({ id: 1, name: 'Owner', columns: 2, rows: 1,
        flowPattern: 'custom', powerFlowPattern: 'custom' });
    // Every cabinet of the peer is on the OWNER's port 1 / circuit 1.
    const peer = gt.screen({ id: 2, name: 'Peer', columns: 2, rows: 1,
        offset_x: 256, flowPattern: 'custom', powerFlowPattern: 'custom' });
    owner.customPortPaths = { 1: [
        { row: 0, col: 0 }, { row: 0, col: 1 },
        { row: 0, col: 0, layerId: 2 }, { row: 0, col: 1, layerId: 2 },
    ] };
    owner.powerCustomPaths = { 1: [
        { row: 0, col: 0 }, { row: 0, col: 1 },
        { row: 0, col: 0, layerId: 2 }, { row: 0, col: 1, layerId: 2 },
    ] };
    // The peer has NO custom paths object at all - the exact edge.
    delete peer.customPortPaths;
    delete peer.powerCustomPaths;
    return [[owner, peer], gt.group([owner, peer])];
}"""


def test_a_peer_with_no_paths_object_still_counts_as_fed_by_its_neighbour(page):
    """One cable across the wall is one port, not one per section."""
    got = page.evaluate("""() => {
        const gt = window.__gt;
        const [layers, group] = (%s)(gt);
        const totals = gt.totals(layers, group);
        return {
            ports: totals.portsPrimary,
            circuits: totals.circuits,
            peerHasPathsKey: 'customPortPaths' in layers[1],
        };
    }""" % _FED_BY_PEER_JS)
    assert got['peerHasPathsKey'] is False, 'the edge under test was not set up'
    assert got['ports'] == 1, f"phantom extra port in the roll-up: {got}"
    assert got['circuits'] == 1, f"phantom extra circuit in the roll-up: {got}"
