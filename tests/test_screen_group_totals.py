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

import json
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
    # The regression guard at the bottom reads the app's OWN live layer, so a
    # neighbour suite that left its state on the shared server must fail HERE,
    # named, not as a TypeError halfway through a 45-line evaluate.
    inherited = pg.evaluate("""() => {
        const layers = window.app.project.layers || [];
        const screens = layers.filter(l => (l.type || 'screen') === 'screen');
        return {
            screens: screens.length,
            grouped: screens.filter(l => !!l.group_id).map(l => l.name),
            groups: (window.app.project.groups || []).length,
        };
    }""")
    assert inherited['screens'] > 0, (
        'inherited a server project with NO screen layer - a previous suite '
        'mutated the shared e2e server without restoring it (see '
        'conftest.server_project_guard): %r' % (inherited,))
    assert not inherited['grouped'] and not inherited['groups'], (
        'inherited group state on the shared e2e server - a previous suite '
        'grouped layers without restoring (see '
        'conftest.server_project_guard): %r' % (inherited,))
    yield pg
    context.close()


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
    """A MIXED-RESOLUTION group still sums its members' own requirements.

    This used to be the rule for every group, on the grounds that automatic
    assignment walks one uniform grid. It is no longer: a group whose members
    are the same panel routes as ONE bigger screen and reports ONE figure - see
    test_a_crossing_group_reports_the_combined_walks_port_count below, where the
    combined figure is deliberately LOWER than this sum.

    This wall is 1m JP5 cabinets (128 x 128 px) above 0.5m panels (64 x 64 px),
    which is exactly the case that may NOT cross: there is no single port
    capacity or circuit load that describes two different panels. So it keeps
    the per-member behaviour, and this assertion is unchanged - it now pins the
    OTHER side of the gate rather than a universal rule.

    Proven against the app's own per-layer answers rather than a constant.
    """
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


# ═════════════════════════════════════════════════════════════════════════
# Automatic routing ACROSS the members (v0.12)
# ═════════════════════════════════════════════════════════════════════════
#
# A group of matching panels is ONE BIGGER SCREEN: the port walk and the circuit
# walk run once over every member's cabinets instead of once per member, and the
# group's first member reports the whole wall while every other member reports
# zero. The rule, and the reason the two halves of it differ:
#
#   data   every member the same panel RESOLUTION (cabinet_width /
#          cabinet_height). Physical millimetres are irrelevant - a 128 x 128
#          cabinet chains the same whether its box is 500 mm or 600 mm.
#   power  the same resolution AND the same panelWatts, because a circuit packs
#          by load.
#
# So a group can legitimately cross for data and not for power. That is not an
# oversight, it is the rule, and it has its own test below.
#
# Every wall here is 128 x 128 cabinets on Brompton 8-bit 60 Hz = 525,000 px a
# port, so a cabinet is 16,384 px and a 6-wide row is 98,304 px: FIVE rows fit
# one port and a sixth does not. Circuits are 208 V x 20 A = 4,160 W at 200 W a
# cabinet, so a 6-wide row is 1,200 W and THREE rows fit one circuit.

def _routes(page, build_js):
    """Per-member and combined figures for a group, plus the same wall UNGROUPED.

    The ungrouped run is the control: it is what the app produced before this
    feature, computed live rather than pinned, so the comparison cannot rot.
    """
    return page.evaluate("""() => {
        const gt = window.__gt;
        const [layers, group] = (%s)(gt);
        const read = (grouped) => {
            layers.forEach(l => { l.group_id = grouped ? group.id : null; });
            return gt.withProject(layers, grouped ? [group] : [], () => {
                const ports = layers.map(l => window.app.getLayerPortsRequired(l));
                const circuits = layers.map(l => window.app.getLayerCircuitsRequired(
                    l, (window.app.calculatePowerAssignments(l).circuits || []).length));
                const portMap = layers.map(l => window.app.calculatePortAssignments(l)
                    .map(a => `${a.layerId === undefined ? l.id : a.layerId}:`
                        + `${a.panel.row},${a.panel.col}#${a.port}`));
                const powerMap = layers.map(l => {
                    const res = window.app.calculatePowerAssignments(l);
                    return (res.circuits || []).map((c, i) => c.map((p, j) =>
                        `${res.layers ? res.layers[i][j].id : l.id}:${p.row},${p.col}`));
                });
                const totals = grouped ? window.app.getGroupTotals(group.id) : null;
                return {
                    ports, circuits, portMap, powerMap,
                    dataPlan: !!window.app.getAutoRoutePlan(layers[0], 'data'),
                    powerPlan: !!window.app.getAutoRoutePlan(layers[0], 'power'),
                    totalPorts: totals ? totals.portsPrimary : ports.reduce((a, b) => a + b, 0),
                    totalCircuits: totals ? totals.circuits : circuits.reduce((a, b) => a + b, 0),
                };
            });
        };
        return { grouped: read(true), apart: read(false) };
    }""" % build_js)


def _crossing_runs(runs, owner_id):
    """The runs (ports or circuits) that carry a cabinet from another member."""
    return [r for r in runs if any(not k.startswith('%s:' % owner_id) for k in r)]


# 6 wide x 6 tall, twice, one directly under the other. Different physical
# cabinet sizes on purpose: 500 mm and 600 mm boxes at the SAME resolution, to
# prove the gate is the panel's pixels and not its millimetres.
TALL_PAIR_JS = """(gt) => {
    const a = gt.screen({ id: 1, name: 'Top', columns: 6, rows: 6,
        panel_width_mm: 500, panel_height_mm: 500,
        flowPattern: 'tl-h', portMappingMode: 'organized' });
    const b = gt.screen({ id: 2, name: 'Bottom', columns: 6, rows: 6,
        panel_width_mm: 600, panel_height_mm: 600, offset_y: 768,
        flowPattern: 'tl-h', portMappingMode: 'organized' });
    return [[a, b], gt.group([a, b])];
}"""


def test_a_same_resolution_group_crosses_for_data(page):
    """One port carries cabinets from both members, and only the first member
    reports the wall's ports."""
    r = _routes(page, TALL_PAIR_JS)
    g = r['grouped']
    assert g['dataPlan'] is True
    assert g['portMap'][1] == [], 'the peer routed its own ports as well'
    crossing = _crossing_runs(_ports_of(g['portMap'][0]), 1)
    assert crossing, f"no port left the first member: {g['portMap'][0]}"
    # Port 2 opens on the first member's last row and finishes four rows into
    # the second's - one port, one chain, straight through the seam.
    assert crossing[0][0] == '1:5,0'
    assert [k.split(':')[0] for k in crossing[0]] == ['1'] * 6 + ['2'] * 24
    assert crossing[0][-1].startswith('2:3,')
    assert g['ports'][1] == 0, 'the peer reported a requirement of its own'
    assert g['totalPorts'] == g['ports'][0]


def test_a_crossing_group_reports_the_combined_walks_port_count(page):
    """THE COUNT CAN DROP, and that is the feature working.

    Each member is 6 x 6 cabinets = twelve 98,304 px rows across the pair.
    Five rows fit a 525,000 px Brompton port and six do not, so:

        apart     6 rows each -> 5 + 1 = TWO ports a member = 4 ports
        together  12 rows     -> 5 + 5 + 2                  = 3 ports

    The port that vanishes is the rounding waste at each member's boundary: the
    lone sixth row of the top member and the lone sixth row of the bottom one
    were each buying a whole port. One wall, one walk, one less port to rack.
    """
    r = _routes(page, TALL_PAIR_JS)
    assert r['apart']['ports'] == [2, 2]
    assert r['apart']['totalPorts'] == 4
    assert r['grouped']['ports'] == [3, 0]
    assert r['grouped']['totalPorts'] == 3
    assert r['grouped']['totalPorts'] < r['apart']['totalPorts']


# 6 wide x 4 tall, twice. Eight 1,200 W rows across the pair at 4,160 W a
# circuit: three rows fit, four do not.
SHORT_PAIR_JS = """(gt) => {
    const a = gt.screen({ id: 1, name: 'Top', columns: 6, rows: 4,
        powerFlowPattern: 'tl-h', powerOrganized: true });
    const b = gt.screen({ id: 2, name: 'Bottom', columns: 6, rows: 4,
        offset_y: 512, powerFlowPattern: 'tl-h', powerOrganized: true });
    return [[a, b], gt.group([a, b])];
}"""


def test_a_same_resolution_same_watts_group_crosses_for_power(page):
    """A circuit carries cabinets from both members, and the count drops.

        apart     4 rows each -> 3 + 1 = TWO circuits a member = 4
        together  8 rows      -> 3 + 3 + 2                     = 3
    """
    r = _routes(page, SHORT_PAIR_JS)
    g = r['grouped']
    assert g['powerPlan'] is True
    assert g['powerMap'][1] == [], 'the peer packed its own circuits as well'
    crossing = _crossing_runs(g['powerMap'][0], 1)
    assert crossing, f"no circuit left the first member: {g['powerMap'][0]}"
    assert crossing[0][0] == '1:3,0'
    assert [k.split(':')[0] for k in crossing[0]] == ['1'] * 6 + ['2'] * 12
    assert crossing[0][-1].startswith('2:1,')
    assert r['apart']['circuits'] == [2, 2]
    assert r['apart']['totalCircuits'] == 4
    assert g['circuits'] == [3, 0]
    assert g['totalCircuits'] == 3


MATCHED_PANEL_MISMATCHED_WATTS_JS = """(gt) => {
    const a = gt.screen({ id: 1, name: 'Top', columns: 6, rows: 6,
        panelWatts: 200, flowPattern: 'tl-h', portMappingMode: 'organized',
        powerFlowPattern: 'tl-h', powerOrganized: true });
    const b = gt.screen({ id: 2, name: 'Bottom', columns: 6, rows: 6,
        panelWatts: 250, offset_y: 768,
        flowPattern: 'tl-h', portMappingMode: 'organized',
        powerFlowPattern: 'tl-h', powerOrganized: true });
    return [[a, b], gt.group([a, b])];
}"""


def test_matching_resolution_but_not_watts_crosses_for_data_and_not_power(page):
    """Same cabinet, different draw - a real wall of one panel type where one
    section is running a different LED module. The data chain does not care what
    a cabinet draws, so it crosses; a circuit is packed by load, so it cannot."""
    r = _routes(page, MATCHED_PANEL_MISMATCHED_WATTS_JS)
    g = r['grouped']
    assert g['dataPlan'] is True
    assert g['powerPlan'] is False
    assert _crossing_runs(_ports_of(g['portMap'][0]), 1), 'data did not cross'
    assert g['ports'] == [3, 0]
    # Power keeps today's per-member behaviour, exactly.
    assert g['powerMap'][1] != [], 'the peer stopped packing its own circuits'
    assert not _crossing_runs(g['powerMap'][0], 1), 'a circuit crossed on mixed watts'
    assert g['circuits'] == r['apart']['circuits']
    assert g['totalCircuits'] == sum(r['apart']['circuits'])


MIXED_RESOLUTION_JS = """(gt) => {
    const a = gt.screen({ id: 1, name: 'JP5', columns: 6, rows: 6,
        cabinet_width: 128, cabinet_height: 128,
        flowPattern: 'tl-h', portMappingMode: 'organized',
        powerFlowPattern: 'tl-h', powerOrganized: true });
    const b = gt.screen({ id: 2, name: 'Half', columns: 12, rows: 12,
        cabinet_width: 64, cabinet_height: 64, offset_y: 768,
        flowPattern: 'tl-h', portMappingMode: 'organized',
        powerFlowPattern: 'tl-h', powerOrganized: true });
    return [[a, b], gt.group([a, b])];
}"""


def test_a_mixed_resolution_group_does_not_cross_at_all(page):
    """1m cabinets over 0.5m ones. Grouping it changes NOTHING about its
    routing - the figures and the maps are the ungrouped ones, cabinet for
    cabinet. Those walls are routed across the seam with custom cables."""
    r = _routes(page, MIXED_RESOLUTION_JS)
    assert r['grouped']['dataPlan'] is False
    assert r['grouped']['powerPlan'] is False
    assert r['grouped']['portMap'] == r['apart']['portMap']
    assert r['grouped']['powerMap'] == r['apart']['powerMap']
    assert r['grouped']['ports'] == r['apart']['ports']
    assert r['grouped']['circuits'] == r['apart']['circuits']
    assert r['grouped']['totalPorts'] == sum(r['apart']['ports'])
    assert r['grouped']['totalCircuits'] == sum(r['apart']['circuits'])


HALF_TILE_PAIR_JS = """(gt) => {
    const a = gt.screen({ id: 1, name: 'Top', columns: 6, rows: 6,
        flowPattern: 'tl-h', portMappingMode: 'organized' });
    const b = gt.screen({ id: 2, name: 'Bottom', columns: 6, rows: 6,
        offset_y: 768, flowPattern: 'tl-h', portMappingMode: 'organized' });
    // The same panel, cropped: the top member's last column and the bottom
    // member's first column are half tiles. NOT a different cabinet spec -
    // cabinet_width / cabinet_height are untouched, which is the whole point.
    a.halfLastColumn = true;
    a.panels.forEach(p => { if (p.col === 5) { p.width = 64; p.halfTile = 'right'; } });
    b.halfFirstColumn = true;
    b.panels.forEach(p => { if (p.col === 0) { p.width = 64; p.halfTile = 'left'; } });
    return [[a, b], gt.group([a, b])];
}"""


def test_half_tiles_do_not_block_crossing(page):
    """A half tile is the same panel cropped, so it can never be the reason a
    wall stops routing as one. The gate compares the panel SPEC and never the
    half-tile flags; the reduced load is already carried per cabinet."""
    r = _routes(page, HALF_TILE_PAIR_JS)
    g = r['grouped']
    assert g['dataPlan'] is True, 'half tiles blocked the crossing'
    assert g['powerPlan'] is True
    assert _crossing_runs(_ports_of(g['portMap'][0]), 1), 'no port crossed'
    assert g['ports'][1] == 0


# The upper half of the wall is the SECOND layer in the list. Index order and
# physical order disagree, which is the whole reason the walk is ranked on a
# position lattice rather than on panel.row.
UPSIDE_DOWN_JS = """(gt) => {
    const lower = gt.screen({ id: 1, name: 'Lower', columns: 6, rows: 6,
        flowPattern: 'tl-h', portMappingMode: 'organized' });
    const upper = gt.screen({ id: 2, name: 'Upper', columns: 6, rows: 6,
        offset_y: -768, flowPattern: 'tl-h', portMappingMode: 'organized' });
    return [[lower, upper], gt.group([lower, upper])];
}"""


def test_the_combined_walk_starts_where_the_wall_starts_not_where_the_list_does(page):
    """A top-left serpentine over this wall has to begin on the UPPER member,
    which is layer 2 and sits at a negative offset. Ordered by panel.row it
    would begin on layer 1's row 0, which is halfway down the wall."""
    r = _routes(page, UPSIDE_DOWN_JS)
    first = _ports_of(r['grouped']['portMap'][0])[0]
    assert first[0] == '2:0,0', f'the walk did not start at the top of the wall: {first[:8]}'
    assert first[6] == '2:1,5', f'the serpentine did not turn at the wall edge: {first[:8]}'
    # It still ENDS on the lower member's bottom-right, and the port that
    # crosses the seam is one port, not two.
    last = _ports_of(r['grouped']['portMap'][0])[-1]
    assert last[-1] == '1:5,0'


def _ports_of(flat):
    """`['1:0,0#1', ...]` regrouped into one list per port number."""
    out = {}
    for key in flat:
        addr, port = key.split('#')
        out.setdefault(int(port), []).append(addr)
    return [out[n] for n in sorted(out)]


# ── "Route data as one screen" - the group's own switch on the crossing ────
#
# Some walls are cabled per section on site no matter what the panels would
# allow, so a group can turn the DATA crossing off (group.routeDataAsOne =
# false, set from the group menu). Off means every member routes exactly as it
# would ungrouped - the walk, the counts, the roll-up and the peer's sidebar
# state all revert together, because the switch sits in the ONE gate they all
# read (_autoCrossMembers). Absent means ON: every group saved before the
# switch existed keeps today's crossing, byte for byte.

ROUTE_ALONE_PAIR_JS = """(gt) => {
    const a = gt.screen({ id: 1, name: 'Top', columns: 6, rows: 6,
        flowPattern: 'tl-h', portMappingMode: 'organized' });
    const b = gt.screen({ id: 2, name: 'Bottom', columns: 6, rows: 6,
        offset_y: 768, flowPattern: 'tl-h', portMappingMode: 'organized' });
    const g = gt.group([a, b]);
    g.routeDataAsOne = false;
    return [[a, b], g];
}"""


def test_route_as_one_off_routes_each_member_exactly_as_ungrouped(page):
    """The same wall test_a_same_resolution_group_crosses_for_data crosses,
    with the switch off: the maps and figures are the UNGROUPED ones, cabinet
    for cabinet, and the peer routes its own ports again."""
    r = _routes(page, ROUTE_ALONE_PAIR_JS)
    g = r['grouped']
    assert g['dataPlan'] is False
    assert g['portMap'] == r['apart']['portMap']
    assert g['ports'] == r['apart']['ports'] == [2, 2]
    assert g['totalPorts'] == 4
    assert g['portMap'][1] != [], 'the peer still routed nothing of its own'
    assert not _crossing_runs(_ports_of(g['portMap'][0]), 1), (
        'a port crossed with the switch off')


def test_route_as_one_off_restores_the_peers_own_sidebar_figure(page):
    """With the switch on, the peer is served by the owner's walk and honestly
    reads 0; off, it reads its own real figure again - not a leftover 0."""
    got = page.evaluate("""() => {
        const gt = window.__gt;
        const [layers, group] = (%s)(gt);
        const read = () => gt.withProject(layers, [group], () => ({
            served: window.app.isServedByPeerRouting(layers[1], 'data'),
            ports: window.app.getLayerPortsRequired(layers[1]),
        }));
        const off = read();           // built with routeDataAsOne: false
        delete group.routeDataAsOne;  // absent = on
        const on = read();
        return { on, off };
    }""" % ROUTE_ALONE_PAIR_JS)
    assert got['on'] == {'served': True, 'ports': 0}
    assert got['off'] == {'served': False, 'ports': 2}


ROUTE_ALONE_POWER_JS = """(gt) => {
    const a = gt.screen({ id: 1, name: 'Top', columns: 6, rows: 4,
        flowPattern: 'tl-h', portMappingMode: 'organized',
        powerFlowPattern: 'tl-h', powerOrganized: true });
    const b = gt.screen({ id: 2, name: 'Bottom', columns: 6, rows: 4,
        offset_y: 512, flowPattern: 'tl-h', portMappingMode: 'organized',
        powerFlowPattern: 'tl-h', powerOrganized: true });
    const g = gt.group([a, b]);
    g.routeDataAsOne = false;
    return [[a, b], g];
}"""


def test_route_as_one_off_leaves_the_power_crossing_alone(page):
    """DATA only. The switch is not a power switch: the same group still packs
    its circuits as one wall while its data cables per member."""
    r = _routes(page, ROUTE_ALONE_POWER_JS)
    g = r['grouped']
    assert g['dataPlan'] is False
    assert g['powerPlan'] is True
    assert g['ports'] == r['apart']['ports']
    assert g['circuits'] == [3, 0]
    assert _crossing_runs(g['powerMap'][0], 1), 'the power crossing was lost'


def test_route_as_one_stored_true_crosses_exactly_as_absent(page):
    """true and absent are the same state - only a stored false turns it off,
    so no migration ever has to write the key."""
    got = page.evaluate("""() => {
        const gt = window.__gt;
        const [layers, group] = (%s)(gt);
        group.routeDataAsOne = true;
        layers.forEach(l => { l.group_id = group.id; });
        return gt.withProject(layers, [group], () => ({
            plan: !!window.app.getAutoRoutePlan(layers[0], 'data'),
            ports: layers.map(l => window.app.getLayerPortsRequired(l)),
        }));
    }""" % TALL_PAIR_JS)
    assert got['plan'] is True
    assert got['ports'] == [3, 0]


# ── The regression bar: NO group, or a group of one ───────────────────────
#
# Every project that has no groups in it, and every group of one, must produce
# exactly what it produced before automatic routing could cross. These are not
# recomputed expectations - they are the literal JSON.stringify bytes this tree
# produced at 1a83348, BEFORE any of the crossing code existed, captured by
# running the battery below against the stashed tree.
#
# The battery is chosen to touch every branch the change reaches into: both Port
# Mapping modes, a rectangle-constraint processor, horizontal-first and
# vertical-first patterns starting from three different corners, half tiles
# (which change a cabinet's load), and a wall with hidden and blank cabinets in
# the middle of it (which change the traversal).

PIN_ROUTES = {
    'org_h':
        '{"ports":[[0,0,1,true,0],[0,1,1,false,16384],[0,2,1,false,32768],[0,3,1,false,49152],[0,4,'
        '1,false,65536],[0,5,1,false,81920],[1,5,1,false,98304],[1,4,1,false,114688],[1,3,1,false,1'
        '31072],[1,2,1,false,147456],[1,1,1,false,163840],[1,0,1,false,180224],[2,0,1,false,196608]'
        ',[2,1,1,false,212992],[2,2,1,false,229376],[2,3,1,false,245760],[2,4,1,false,262144],[2,5,'
        '1,false,278528],[3,5,1,false,294912],[3,4,1,false,311296],[3,3,1,false,327680],[3,2,1,fals'
        'e,344064],[3,1,1,false,360448],[3,0,1,false,376832],[4,0,1,false,393216],[4,1,1,false,4096'
        '00],[4,2,1,false,425984],[4,3,1,false,442368],[4,4,1,false,458752],[4,5,1,false,475136],[5'
        ',0,2,true,0],[5,1,2,false,16384],[5,2,2,false,32768],[5,3,2,false,49152],[5,4,2,false,6553'
        '6],[5,5,2,false,81920]],"autoPorts":2,"portsRequired":2,"power":[[[0,0],[0,1],[0,2],[0,3],'
        '[0,4],[0,5],[1,5],[1,4],[1,3],[1,2],[1,1],[1,0],[2,0],[2,1],[2,2],[2,3],[2,4],[2,5]],[[3,0'
        '],[3,1],[3,2],[3,3],[3,4],[3,5],[4,5],[4,4],[4,3],[4,2],[4,1],[4,0],[5,0],[5,1],[5,2],[5,3'
        '],[5,4],[5,5]]],"circuits":2,"soca":"[{\\"soca\\":1,\\"number\\":1,\\"name\\":\\"S1\\",\\"distroId\\'
        '":null,\\"legs\\":[{\\"leg\\":1,\\"circuit\\":1,\\"label\\":\\"S1-1\\",\\"tiles\\":18,\\"watts\\":3600,\\'
        '"amps\\":17.307692307692307,\\"x1\\":0,\\"x2\\":768},{\\"leg\\":2,\\"circuit\\":2,\\"label\\":\\"S1-2\\'
        '",\\"tiles\\":18,\\"watts\\":3600,\\"amps\\":17.307692307692307,\\"x1\\":0,\\"x2\\":768}],\\"watts\\":'
        '7200,\\"x1\\":0,\\"x2\\":768,\\"amps\\":34.61538461538461,\\"length\\":null}]"}',
    'org_v':
        '{"ports":[[6,4,1,true,0],[5,4,1,false,16384],[4,4,1,false,32768],[3,4,1,false,49152],[2,4,'
        '1,false,65536],[1,4,1,false,81920],[0,4,1,false,98304],[0,3,1,false,114688],[1,3,1,false,1'
        '31072],[2,3,1,false,147456],[3,3,1,false,163840],[4,3,1,false,180224],[5,3,1,false,196608]'
        ',[6,3,1,false,212992],[6,2,1,false,229376],[5,2,1,false,245760],[4,2,1,false,262144],[3,2,'
        '1,false,278528],[2,2,1,false,294912],[1,2,1,false,311296],[0,2,1,false,327680],[0,1,1,fals'
        'e,344064],[1,1,1,false,360448],[2,1,1,false,376832],[3,1,1,false,393216],[4,1,1,false,4096'
        '00],[5,1,1,false,425984],[6,1,1,false,442368],[6,0,2,true,0],[5,0,2,false,16384],[4,0,2,fa'
        'lse,32768],[3,0,2,false,49152],[2,0,2,false,65536],[1,0,2,false,81920],[0,0,2,false,98304]'
        '],"autoPorts":2,"portsRequired":2,"power":[[[6,0],[5,0],[4,0],[3,0],[2,0],[1,0],[0,0],[0,1'
        '],[1,1],[2,1],[3,1],[4,1],[5,1],[6,1]],[[6,2],[5,2],[4,2],[3,2],[2,2],[1,2],[0,2],[0,3],[1'
        ',3],[2,3],[3,3],[4,3],[5,3],[6,3]],[[6,4],[5,4],[4,4],[3,4],[2,4],[1,4],[0,4]]],"circuits"'
        ':3,"soca":"[{\\"soca\\":1,\\"number\\":1,\\"name\\":\\"S1\\",\\"distroId\\":null,\\"legs\\":[{\\"leg\\":'
        '1,\\"circuit\\":1,\\"label\\":\\"S1-1\\",\\"tiles\\":14,\\"watts\\":2100,\\"amps\\":19.09090909090909,'
        '\\"x1\\":0,\\"x2\\":256},{\\"leg\\":2,\\"circuit\\":2,\\"label\\":\\"S1-2\\",\\"tiles\\":14,\\"watts\\":21'
        '00,\\"amps\\":19.09090909090909,\\"x1\\":256,\\"x2\\":512},{\\"leg\\":3,\\"circuit\\":3,\\"label\\":\\"'
        'S1-3\\",\\"tiles\\":7,\\"watts\\":1050,\\"amps\\":9.545454545454545,\\"x1\\":512,\\"x2\\":640}],\\"wat'
        'ts\\":5250,\\"x1\\":0,\\"x2\\":640,\\"amps\\":47.72727272727273,\\"length\\":null}]"}',
    'maxcap':
        '{"ports":[[0,6,1,true,0],[0,5,1,false,16384],[0,4,1,false,32768],[0,3,1,false,49152],[0,2,'
        '1,false,65536],[0,1,1,false,81920],[0,0,1,false,98304],[1,0,1,false,114688],[1,1,1,false,1'
        '31072],[1,2,1,false,147456],[1,3,1,false,163840],[1,4,1,false,180224],[1,5,1,false,196608]'
        ',[1,6,1,false,212992],[2,6,1,false,229376],[2,5,1,false,245760],[2,4,1,false,262144],[2,3,'
        '1,false,278528],[2,2,1,false,294912],[2,1,1,false,311296],[2,0,1,false,327680],[3,0,1,fals'
        'e,344064],[3,1,1,false,360448],[3,2,1,false,376832],[3,3,1,false,393216],[3,4,1,false,4096'
        '00],[3,5,1,false,425984],[3,6,1,false,442368]],"autoPorts":1,"portsRequired":1,"power":[[['
        '0,6],[0,5],[0,4],[0,3],[0,2],[0,1],[0,0],[1,0],[1,1],[1,2],[1,3],[1,4],[1,5],[1,6],[2,6],['
        '2,5],[2,4],[2,3],[2,2],[2,1]],[[2,0],[3,0],[3,1],[3,2],[3,3],[3,4],[3,5],[3,6]]],"circuits'
        '":2,"soca":"[{\\"soca\\":1,\\"number\\":1,\\"name\\":\\"S1\\",\\"distroId\\":null,\\"legs\\":[{\\"leg\\"'
        ':1,\\"circuit\\":1,\\"label\\":\\"S1-1\\",\\"tiles\\":20,\\"watts\\":4000,\\"amps\\":19.23076923076923'
        ',\\"x1\\":0,\\"x2\\":896},{\\"leg\\":2,\\"circuit\\":2,\\"label\\":\\"S1-2\\",\\"tiles\\":8,\\"watts\\":16'
        '00,\\"amps\\":7.6923076923076925,\\"x1\\":0,\\"x2\\":896}],\\"watts\\":5600,\\"x1\\":0,\\"x2\\":896,\\"'
        'amps\\":26.923076923076923,\\"length\\":null}]"}',
    'armor':
        '{"ports":[[0,0,1,true,0],[1,0,1,false,16384],[2,0,1,false,32768],[3,0,1,false,49152],[4,0,'
        '1,false,65536],[4,1,1,false,81920],[3,1,1,false,98304],[2,1,1,false,114688],[1,1,1,false,1'
        '31072],[0,1,1,false,147456],[0,2,1,false,163840],[1,2,1,false,180224],[2,2,1,false,196608]'
        ',[3,2,1,false,212992],[4,2,1,false,229376],[4,3,1,false,245760],[3,3,1,false,262144],[2,3,'
        '1,false,278528],[1,3,1,false,294912],[0,3,1,false,311296],[0,4,1,false,327680],[1,4,1,fals'
        'e,344064],[2,4,1,false,360448],[3,4,1,false,376832],[4,4,1,false,393216],[4,5,1,false,4096'
        '00],[3,5,1,false,425984],[2,5,1,false,442368],[1,5,1,false,458752],[0,5,1,false,475136],[0'
        ',6,1,false,491520],[1,6,1,false,507904],[2,6,1,false,524288],[3,6,1,false,540672],[4,6,1,f'
        'alse,557056],[4,7,1,false,573440],[3,7,1,false,589824],[2,7,1,false,606208],[1,7,1,false,6'
        '22592],[0,7,1,false,638976]],"autoPorts":1,"portsRequired":1,"power":[[[0,0],[1,0],[2,0],['
        '3,0],[4,0],[4,1],[3,1],[2,1],[1,1],[0,1],[0,2],[1,2],[2,2],[3,2],[4,2],[4,3],[3,3],[2,3],['
        '1,3],[0,3]],[[0,4],[1,4],[2,4],[3,4],[4,4],[4,5],[3,5],[2,5],[1,5],[0,5],[0,6],[1,6],[2,6]'
        ',[3,6],[4,6],[4,7],[3,7],[2,7],[1,7],[0,7]]],"circuits":2,"soca":"[{\\"soca\\":1,\\"number\\":'
        '1,\\"name\\":\\"S1\\",\\"distroId\\":null,\\"legs\\":[{\\"leg\\":1,\\"circuit\\":1,\\"label\\":\\"S1-1\\",'
        '\\"tiles\\":20,\\"watts\\":4000,\\"amps\\":19.23076923076923,\\"x1\\":0,\\"x2\\":512},{\\"leg\\":2,\\"c'
        'ircuit\\":2,\\"label\\":\\"S1-2\\",\\"tiles\\":20,\\"watts\\":4000,\\"amps\\":19.23076923076923,\\"x1\\'
        '":512,\\"x2\\":1024}],\\"watts\\":8000,\\"x1\\":0,\\"x2\\":1024,\\"amps\\":38.46153846153846,\\"lengt'
        'h\\":null}]"}',
    'halves':
        '{"ports":[[0,0,1,true,0],[0,1,1,false,8192],[0,2,1,false,24576],[0,3,1,false,40960],[0,4,1'
        ',false,57344],[0,5,1,false,73728],[1,5,1,false,90112],[1,4,1,false,106496],[1,3,1,false,12'
        '2880],[1,2,1,false,139264],[1,1,1,false,155648],[1,0,1,false,172032],[2,0,1,false,180224],'
        '[2,1,1,false,188416],[2,2,1,false,204800],[2,3,1,false,221184],[2,4,1,false,237568],[2,5,1'
        ',false,253952],[3,5,1,false,270336],[3,4,1,false,286720],[3,3,1,false,303104],[3,2,1,false'
        ',319488],[3,1,1,false,335872],[3,0,1,false,352256]],"autoPorts":1,"portsRequired":1,"power'
        '":[[[0,0],[0,1],[0,2],[0,3],[0,4],[0,5],[1,5],[1,4],[1,3],[1,2],[1,1],[1,0],[2,0],[2,1],[2'
        ',2],[2,3],[2,4],[2,5],[3,5],[3,4],[3,3]],[[3,2],[3,1],[3,0]]],"circuits":2,"soca":"[{\\"soc'
        'a\\":1,\\"number\\":1,\\"name\\":\\"S1\\",\\"distroId\\":null,\\"legs\\":[{\\"leg\\":1,\\"circuit\\":1,\\"'
        'label\\":\\"S1-1\\",\\"tiles\\":21,\\"watts\\":3990,\\"amps\\":19.182692307692307,\\"x1\\":0,\\"x2\\":7'
        '68},{\\"leg\\":2,\\"circuit\\":2,\\"label\\":\\"S1-2\\",\\"tiles\\":3,\\"watts\\":530,\\"amps\\":2.54807'
        '6923076923,\\"x1\\":0,\\"x2\\":384}],\\"watts\\":4520,\\"x1\\":0,\\"x2\\":768,\\"amps\\":21.7307692307'
        '6923,\\"length\\":null}]"}',
    'holes':
        '{"ports":[[4,0,1,true,0],[4,1,1,false,16384],[4,2,1,false,32768],[4,3,1,false,49152],[4,4,'
        '1,false,65536],[4,5,1,false,81920],[3,5,1,false,98304],[3,4,1,false,114688],[3,3,1,false,1'
        '31072],[3,2,1,false,147456],[3,1,1,false,163840],[3,0,1,false,180224],[2,0,1,false,196608]'
        ',[2,1,1,false,212992],[2,2,1,false,229376],[1,5,1,false,245760],[1,4,1,false,262144],[1,3,'
        '1,false,278528],[1,2,1,false,294912],[1,1,1,false,311296],[1,0,1,false,327680],[0,0,1,fals'
        'e,344064],[0,1,1,false,360448],[0,2,1,false,376832],[0,3,1,false,393216],[0,4,1,false,4096'
        '00],[0,5,1,false,425984]],"autoPorts":1,"portsRequired":1,"power":[[[4,0],[4,1],[4,2],[4,3'
        '],[4,4],[4,5],[3,5],[3,4],[3,3],[3,2],[3,1],[3,0],[2,0],[2,1],[2,2]],[[1,0],[1,1],[1,2],[1'
        ',3],[1,4],[1,5],[0,5],[0,4],[0,3],[0,2],[0,1],[0,0]]],"circuits":2,"soca":"[{\\"soca\\":1,\\"'
        'number\\":1,\\"name\\":\\"S1\\",\\"distroId\\":null,\\"legs\\":[{\\"leg\\":1,\\"circuit\\":1,\\"label\\":'
        '\\"S1-1\\",\\"tiles\\":15,\\"watts\\":3000,\\"amps\\":14.423076923076923,\\"x1\\":0,\\"x2\\":768},{\\"l'
        'eg\\":2,\\"circuit\\":2,\\"label\\":\\"S1-2\\",\\"tiles\\":12,\\"watts\\":2400,\\"amps\\":11.5384615384'
        '61538,\\"x1\\":0,\\"x2\\":768}],\\"watts\\":5400,\\"x1\\":0,\\"x2\\":768,\\"amps\\":25.96153846153846,'
        '\\"length\\":null}]"}',
    'group_of_one':
        '{"ports":[[0,0,1,true,0],[0,1,1,false,16384],[0,2,1,false,32768],[0,3,1,false,49152],[0,4,'
        '1,false,65536],[0,5,1,false,81920],[1,5,1,false,98304],[1,4,1,false,114688],[1,3,1,false,1'
        '31072],[1,2,1,false,147456],[1,1,1,false,163840],[1,0,1,false,180224],[2,0,1,false,196608]'
        ',[2,1,1,false,212992],[2,2,1,false,229376],[2,3,1,false,245760],[2,4,1,false,262144],[2,5,'
        '1,false,278528],[3,5,1,false,294912],[3,4,1,false,311296],[3,3,1,false,327680],[3,2,1,fals'
        'e,344064],[3,1,1,false,360448],[3,0,1,false,376832],[4,0,1,false,393216],[4,1,1,false,4096'
        '00],[4,2,1,false,425984],[4,3,1,false,442368],[4,4,1,false,458752],[4,5,1,false,475136],[5'
        ',0,2,true,0],[5,1,2,false,16384],[5,2,2,false,32768],[5,3,2,false,49152],[5,4,2,false,6553'
        '6],[5,5,2,false,81920]],"autoPorts":2,"portsRequired":2,"power":[[[0,0],[0,1],[0,2],[0,3],'
        '[0,4],[0,5],[1,5],[1,4],[1,3],[1,2],[1,1],[1,0],[2,0],[2,1],[2,2],[2,3],[2,4],[2,5]],[[3,0'
        '],[3,1],[3,2],[3,3],[3,4],[3,5],[4,5],[4,4],[4,3],[4,2],[4,1],[4,0],[5,0],[5,1],[5,2],[5,3'
        '],[5,4],[5,5]]],"circuits":2,"soca":"[{\\"soca\\":1,\\"number\\":1,\\"name\\":\\"S1\\",\\"distroId\\'
        '":null,\\"legs\\":[{\\"leg\\":1,\\"circuit\\":1,\\"label\\":\\"S1-1\\",\\"tiles\\":18,\\"watts\\":3600,\\'
        '"amps\\":17.307692307692307,\\"x1\\":0,\\"x2\\":768},{\\"leg\\":2,\\"circuit\\":2,\\"label\\":\\"S1-2\\'
        '",\\"tiles\\":18,\\"watts\\":3600,\\"amps\\":17.307692307692307,\\"x1\\":0,\\"x2\\":768}],\\"watts\\":'
        '7200,\\"x1\\":0,\\"x2\\":768,\\"amps\\":34.61538461538461,\\"length\\":null}]"}',
}


ROUTE_BATTERY_JS = """
    const gt = window.__gt;
    const mk = {
        org_h: () => gt.screen({ id: 1, name: 'OrgH', columns: 6, rows: 6,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-h', powerOrganized: true }),
        org_v: () => gt.screen({ id: 1, name: 'OrgV', columns: 5, rows: 7,
            flowPattern: 'br-v', portMappingMode: 'organized',
            powerFlowPattern: 'bl-v', powerOrganized: true,
            panelWatts: 150, powerVoltage: 110, powerAmperage: 20 }),
        maxcap: () => gt.screen({ id: 1, name: 'Max', columns: 7, rows: 4,
            flowPattern: 'tr-h', portMappingMode: 'maximize',
            powerFlowPattern: 'tr-h', powerOrganized: false, powerMaximize: true }),
        armor: () => gt.screen({ id: 1, name: 'Armor', columns: 8, rows: 5,
            processorType: 'novastar-armor', flowPattern: 'tl-v',
            portMappingMode: 'organized', powerFlowPattern: 'tl-v',
            powerOrganized: true }),
        halves: () => {
            const s = gt.screen({ id: 1, name: 'Halves', columns: 6, rows: 4,
                flowPattern: 'tl-h', portMappingMode: 'organized' });
            s.halfFirstColumn = true;
            s.panels.forEach(p => { if (p.col === 0) { p.width = 64; p.halfTile = 'left'; } });
            return s;
        },
        holes: () => {
            const s = gt.screen({ id: 1, name: 'Holes', columns: 6, rows: 5,
                flowPattern: 'bl-h', portMappingMode: 'organized',
                powerFlowPattern: 'bl-h', powerOrganized: true });
            s.panels.forEach(p => { if (p.row === 2 && p.col > 2) p.hidden = true; });
            s.panels.forEach(p => { if (p.row === 0 && p.col === 0) p.blank = true; });
            return s;
        },
    };
    const read = (s) => JSON.stringify({
        ports: window.app.calculatePortAssignments(s).map(a =>
            [a.panel.row, a.panel.col, a.port, a.isPortStart, a.pixelIndex]),
        autoPorts: s._autoPortsRequired,
        portsRequired: window.app.getLayerPortsRequired(s),
        power: window.app.calculatePowerAssignments(s).circuits.map(
            c => c.map(p => [p.row, p.col])),
        circuits: window.app.screenCircuitCount(s),
        soca: JSON.stringify(window.app.getSocaPlan(s)),
    });
    const out = {};
    for (const key of Object.keys(mk)) {
        const s = mk[key]();
        out[key] = gt.withProject([s], [], () => read(s));
    }
    // A GROUP OF ONE is not a group. It must behave exactly like no group.
    const solo = mk.org_h();
    solo.group_id = 'g1';
    out.group_of_one = gt.withProject([solo], [gt.group([solo])], () => read(solo));
    return out;
"""


def test_an_ungrouped_project_routes_exactly_as_it_did_before(page):
    """Ports, circuits, the soca plan and both requirement figures, byte for
    byte against the capture taken before the crossing code existed."""
    out = page.evaluate("() => {%s}" % ROUTE_BATTERY_JS)
    for key, pin in PIN_ROUTES.items():
        assert out[key] == pin, f'{key}: an ungrouped screen\'s routing moved'
        assert json.loads(out[key]) == json.loads(pin)   # readable diff


def test_a_group_of_one_routes_exactly_as_an_ungrouped_screen(page):
    """Same wall, same everything - the only difference is a group_id and a
    one-member group. getAutoRoutePlan needs two members before it does
    anything, so this is the same code path an ungrouped screen takes."""
    out = page.evaluate("() => {%s}" % ROUTE_BATTERY_JS)
    assert out['group_of_one'] == out['org_h']
    assert out['group_of_one'] == PIN_ROUTES['org_h']
