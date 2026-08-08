"""v0.11.0 numbers audit - independent re-derivation of every figure that
decides how many Ethernet ports, power circuits and kilograms a crew plans for.

Nothing here is a self-consistency check. Each expectation is computed by hand
from the stated formula (or from the manufacturer wording quoted in the source)
and then compared with what the app produces.

Part 1 is pure Python: it parses portCapacityTables straight out of
app-core.js and re-derives every cell.
Part 2 drives the real app in a browser, using the synthetic-project pattern
from tests/test_screen_group_totals.py.

Run alone (the harness hard-codes port 15789):
    python -m pytest tests/test_audit_numbers.py -v --browser chromium
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

APP_CORE = os.path.join(
    os.path.dirname(__file__), '..', 'src', 'static', 'js', 'app-core.js')


# ── Part 1: the capacity tables, re-derived from the published formulas ──

def _parse_port_capacity_tables():
    src = open(APP_CORE).read()
    i = src.index('portCapacityTables = {')
    start = src.index('{', i)
    depth = 0
    for j in range(start, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                end = j
                break
    blob = re.sub(r'//[^\n]*', '', src[start:end + 1])
    tables = {}
    for m in re.finditer(r"'([a-z0-9.\-]+)':\s*\{(.*?)\n\s*\}", blob, re.S):
        t = {}
        for bm in re.finditer(r'(\d+):\s*\{([^}]*)\}', m.group(2)):
            t[int(bm.group(1))] = {
                int(a): int(b)
                for a, b in re.findall(r'(\d+)\s*:\s*(\d+)', bm.group(2))
            }
        tables[m.group(1)] = t
    return tables


TABLES = _parse_port_capacity_tables()


def _check_family(name, multipliers, bits_per_sec, efficiency, tol_pct):
    """cap x multiplier x frameRate < link x efficiency  ->  cap = link*eff/(mult*fr)"""
    bad = []
    for bd, row in sorted(TABLES[name].items()):
        mult = multipliers[bd]
        for fr, cap in sorted(row.items()):
            expect = bits_per_sec * efficiency[bd] / (mult * fr)
            delta = (cap - expect) / expect * 100.0
            if abs(delta) > tol_pct:
                bad.append(
                    '%s %d-bit %dHz: table=%d formula=%.0f (%+.4f%%)'
                    % (name, bd, fr, cap, expect, delta))
    return bad


# THE RULE, owner's words: "whatever helios and brompton say goes for each
# option". The manufacturer's PUBLISHED table is authoritative. A formula is
# only ever a cross-check for spotting a transcription slip - where the two
# disagree, the published figure wins and the code is NOT adjusted to fit the
# curve. Vendors round, and sometimes to a real hardware constraint rather than
# to arithmetic.
#
# So a cell that departs from the formula is pinned HERE, by value, with the
# deviation stated. That keeps the cross-check alive for every other cell: a
# genuine typo still fails this file, while a known published value does not.
PUBLISHED_OVERRIDES = {
    # NovaStar's own table reads 612,374 where 5e9 x 0.85 / (48 x 144) gives
    # 614,873 - a 0.41% departure, in the conservative direction (slightly less
    # capacity than the formula implies, so slightly more ports).
    ('novastar-5g', 12, 144): 612374,
}


def test_novastar_5g_matches_novastars_published_table():
    """8-bit x24 @0.85, 10-bit x32 @0.88, 12-bit x48 @0.85 over a 5 Gbit link.

    Hand check of the two cells v0.11.0 corrected:
      12-bit 60 Hz = 5e9 x 0.85 / (48 x 60) = 1,475,694 -> table 1,475,600
       8-bit 60 Hz = 5e9 x 0.85 / (24 x 60) = 2,951,389 -> table 2,951,200
    """
    assert TABLES['novastar-5g'][12][60] == 1475600
    assert TABLES['novastar-5g'][8][60] == 2951200
    assert TABLES['novastar-5g'][8][60] == 2 * TABLES['novastar-5g'][12][60]
    # Pinned by value: this is what NovaStar publish, not what the formula says.
    assert TABLES['novastar-5g'][12][144] == PUBLISHED_OVERRIDES[('novastar-5g', 12, 144)]
    bad = [b for b in _check_family('novastar-5g', {8: 24, 10: 32, 12: 48}, 5e9,
                                    {8: 0.85, 10: 0.88, 12: 0.85}, 0.05)
           if '12-bit 144Hz' not in b]
    assert not bad, '\n'.join(bad)


def test_novastar_1g_families_match_a_24_32_48_x_095_derivation():
    """COEX 1G: 24/32/48 at 95% of 1 Gbit. Armor: 24 for 8-bit, 48 for 10 and 12."""
    assert not _check_family('novastar-coex-1g', {8: 24, 10: 32, 12: 48}, 1e9,
                             {8: 0.95, 10: 0.95, 12: 0.95}, 0.01)
    assert not _check_family('novastar-armor', {8: 24, 10: 48, 12: 48}, 1e9,
                             {8: 0.95, 10: 0.95, 12: 0.95}, 0.01)


def test_every_table_row_scales_as_one_over_frame_rate():
    """capacity x frame rate must be flat across a row for a bandwidth model.

    Megapixel is exempt and listed separately - its published table is not a
    1/fr curve, which is exactly why it cannot be re-derived here.
    """
    offenders = []
    for name, table in TABLES.items():
        if name.startswith('megapixel'):
            continue
        for bd, row in sorted(table.items()):
            # Cells the manufacturer publishes off-curve are excluded from the
            # spread, not "corrected" into it - see PUBLISHED_OVERRIDES.
            products = {fr: cap * fr for fr, cap in row.items()
                        if (name, bd, fr) not in PUBLISHED_OVERRIDES}
            if not products:
                continue
            lo, hi = min(products.values()), max(products.values())
            spread = (hi - lo) / lo * 100.0
            if spread > 0.05:
                worst = min(products, key=lambda fr: products[fr])
                offenders.append(
                    '%s %d-bit spread=%.4f%% (worst cell %dHz = %d, '
                    'implies %.0f)' % (name, bd, spread, worst, row[worst],
                                       hi / worst))
    assert not offenders, '\n'.join(offenders)


# brompton-ull is the RETIRED table, kept only so a stale value that slipped
# past the migration still resolves to a real capacity. The live path is
# brompton + Low Latency, which halves and FLOORS. Two of its 48 cells round up
# instead, so the retired table and the live path differ by a single pixel per
# port there - about 1 part in 73,000, far too small to move a cabinet count.
#
# Left as published rather than floored, per the rule that a manufacturer's
# figure is not adjusted to fit our arithmetic. Pinned by value so the gap
# cannot silently widen.
BROMPTON_ULL_PUBLISHED_ROUNDING = {
    (12, 144): 72917,   # floor(145833 / 2) = 72916
    (12, 192): 54688,   # floor(109375 / 2) = 54687
}


def test_brompton_ull_table_is_the_brompton_column_halved():
    """Every cell is the halved figure, bar two the retired table publishes
    rounded up - those are pinned by value above."""
    bad = []
    for bd, row in sorted(TABLES['brompton'].items()):
        for fr, cap in sorted(row.items()):
            ull = TABLES['brompton-ull'][bd][fr]
            pinned = BROMPTON_ULL_PUBLISHED_ROUNDING.get((bd, fr))
            if pinned is not None:
                if ull != pinned:
                    bad.append('brompton-ull %d-bit %dHz = %d, published %d'
                               % (bd, fr, ull, pinned))
                continue
            if ull != cap // 2:
                bad.append('brompton-ull %d-bit %dHz = %d, floor(%d/2) = %d'
                           % (bd, fr, ull, cap, cap // 2))
    assert not bad, '\n'.join(bad)


def test_the_two_rounded_ull_cells_cannot_change_a_cabinet_count():
    """The reason the 1-pixel gap above is acceptable, asserted rather than
    assumed: a cabinet is at minimum 64x64 = 4,096 px, so one pixel of port
    capacity cannot add or remove one."""
    for (bd, fr), pinned in BROMPTON_ULL_PUBLISHED_ROUNDING.items():
        live = TABLES['brompton'][bd][fr] // 2
        assert abs(pinned - live) == 1, (bd, fr, pinned, live)
        smallest_cabinet_px = 64 * 64
        assert abs(pinned - live) < smallest_cabinet_px


def test_megapixel_helios_figures_are_not_derivable_from_anything_in_the_repo():
    """Documented as UNVERIFIABLE, deliberately.

    The HELIOS rows do not follow a 1/frame-rate bandwidth curve: capacity x
    frame rate falls ~19% from 24 Hz to 240 Hz. There is no formula in the repo
    that reproduces them, so the only check possible is that the one figure
    v0.11.0 claims to have corrected is present. Everything else must be
    checked against the cited User Guide by a human.
    """
    assert TABLES['megapixel-1g'][12][60] == 401000
    products = {fr: cap * fr for fr, cap in TABLES['megapixel-1g'][12].items()}
    spread = (max(products.values()) - min(products.values())) / min(products.values())
    assert spread > 0.1, (
        'HELIOS now looks like a 1/fr curve - if it is, it CAN be re-derived '
        'and this test should be replaced with a real derivation')


# ── Part 2: the app itself ───────────────────────────────────────────────

# NOTE: no module-level importorskip - Part 1 above is pure Python and must
# run even where Playwright is not installed. conftest's pw_browser fixture
# does the skip for Part 2.


@pytest.fixture(scope='module')
def page(e2e_server, pw_browser):
    pytest.importorskip('playwright.sync_api', reason='playwright not installed')
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    pg.evaluate(HELPERS_JS)
    return pg


HELPERS_JS = """
window.__aud = {
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'S', type: 'screen', visible: true,
            columns: 2, rows: 2,
            cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0, canvas_id: 'c1',
            panel_weight: 20, weight_unit: 'kg',
            panelWatts: 200, powerVoltage: 110, powerAmperage: 20,
            processorType: 'brompton', bitDepth: 8, frameRate: 60,
            lowLatency: false,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-h', powerOrganized: false, powerMaximize: false,
            group_id: null,
        }, opts || {});
        const panels = [];
        let n = 1;
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    id: n, number: n, row: r, col: c,
                    x: o.offset_x + c * o.cabinet_width,
                    y: o.offset_y + r * o.cabinet_height,
                    width: o.cabinet_width, height: o.cabinet_height,
                    hidden: false, blank: false, halfTile: 'none',
                });
                n++;
            }
        }
        o.panels = panels;
        return o;
    },
    withProject(layers, groups, fn) {
        const saved = window.app.project;
        window.app.project = {
            layers: layers,
            groups: groups || [],
            canvases: [{ id: 'c1', name: 'C1', raster_width: 4096, raster_height: 2160 }],
            raster_width: 4096, raster_height: 2160,
        };
        try { return fn(); } finally { window.app.project = saved; }
    },
    group(layers, id) {
        const gid = id || 'g1';
        layers.forEach(l => { l.group_id = gid; });
        return { id: gid, name: 'Wall', layer_ids: layers.map(l => l.id) };
    },
};
"""


def _js(page, body):
    return page.evaluate('() => { const A = window.__aud; %s }' % body)


# ── low latency scope: no rule may leak between processors ───────────────

ALL_PROCESSORS = ['novastar-armor', 'novastar-coex-1g', 'novastar-5g',
                  'brompton', 'megapixel-1g', 'megapixel-2.5g']


def test_brompton_halving_applies_to_brompton_and_to_nothing_else(page):
    got = _js(page, """
        const out = {};
        %s.forEach(p => {
            const off = window.app.calculatePortCapacity(8, 60, p, false);
            const on  = window.app.calculatePortCapacity(8, 60, p, true);
            out[p] = { off, on, ratio: off > 0 ? on / off : null };
        });
        return out;
    """ % ALL_PROCESSORS)
    # Brompton 8-bit 60 Hz: 525,000 -> 262,500
    assert got['brompton']['off'] == 525000
    assert got['brompton']['on'] == 262500
    for proc in ALL_PROCESSORS:
        if proc == 'brompton':
            continue
        assert got[proc]['on'] == got[proc]['off'], (
            '%s: Low Latency changed pixels/port (%s -> %s); halving is a '
            'Brompton rule only' % (proc, got[proc]['off'], got[proc]['on']))


def test_y_derate_applies_to_novastar_only(page):
    got = _js(page, """
        const out = {};
        %s.forEach(p => {
            const l = A.screen({ processorType: p, lowLatency: true });
            out[p] = !!window.app.getLowLatencyGeometry(l);
        });
        return out;
    """ % ALL_PROCESSORS)
    assert got == {
        'novastar-armor': True, 'novastar-coex-1g': True, 'novastar-5g': True,
        'brompton': False, 'megapixel-1g': False, 'megapixel-2.5g': False,
    }, got


def test_128px_minimum_load_width_applies_to_novastar_5g_only(page):
    got = _js(page, """
        const out = {};
        %s.forEach(p => {
            out[p] = {
                min: window.app.novastarMinLoadWidth(p),
                // a 64 px wide x 256 px tall port on a 1,000,000 px limit
                penalised: window.app.minLoadWidthPortCapacity(1000000, p, 64, 256),
            };
        });
        return out;
    """ % ALL_PROCESSORS)
    # (128 - 64) x 256 = 16,384 px lost on 5G, nothing anywhere else.
    assert got['novastar-5g'] == {'min': 128, 'penalised': 1000000 - 16384}
    for proc in ALL_PROCESSORS:
        if proc == 'novastar-5g':
            continue
        assert got[proc] == {'min': 0, 'penalised': 1000000}, (proc, got[proc])


def test_5g_narrow_port_penalty_is_a_property_of_the_port_not_of_low_latency(page):
    """NovaStar print the 128 px note under the general capacity table, and
    calculatePortAssignments reads novastarMinLoadWidth unconditionally. A 5G
    screen with Low Latency OFF must still be penalised."""
    got = _js(page, """
        // one column of 64 px wide cabinets: load width 64, so every port
        // pays (128 - 64) x its own height.
        const mk = (ll) => {
            const s = A.screen({ id: 1, columns: 1, rows: 2,
                                 cabinet_width: 64, cabinet_height: 128,
                                 processorType: 'novastar-5g', bitDepth: 12,
                                 frameRate: 60, lowLatency: ll,
                                 flowPattern: 'tl-v', portMappingMode: 'max' });
            return A.withProject([s], [], () => {
                window.app.calculatePortAssignments(s);
                return window.canvasRenderer.getPortCapacityForPanels(s, s.panels);
            });
        };
        return { off: mk(false), on: mk(true) };
    """)
    table = 1475600           # 5G 12-bit 60 Hz
    penalty = (128 - 64) * 256   # port box is 64 wide x 256 tall
    assert got['off'] == table - penalty, got
    # Low Latency ON: the port starts at Y = 0 so (1 - 0/H) = 1, then the same
    # penalty. Identical figure - the penalty is not a low-latency cost.
    assert got['on'] == table - penalty, got


def test_5g_order_of_operations_is_y_derate_then_narrow_port_penalty(page):
    """A 5G port 64 px wide x 256 px tall whose top sits at Y = 1080 on a
    2160 px canvas, 12-bit 60 Hz:
        table                     1,475,600
        x (1 - 1080/2160) = 0.5     737,800
        - (128 - 64) x 256         - 16,384
                                  = 721,416
    Penalty-first would give (1,475,600 - 16,384) x 0.5 = 729,608, which is
    8,192 px MORE capacity than the port has.
    """
    got = _js(page, """
        const s = A.screen({ id: 1, columns: 1, rows: 2,
                             cabinet_width: 64, cabinet_height: 128,
                             offset_y: 1080,
                             processorType: 'novastar-5g', bitDepth: 12,
                             frameRate: 60, lowLatency: true,
                             flowPattern: 'tl-v', portMappingMode: 'max' });
        return A.withProject([s], [], () =>
            window.canvasRenderer.getPortCapacityForPanels(s, s.panels));
    """)
    assert got == 721416, got


def test_y_derate_arithmetic_is_one_minus_y_over_h(page):
    """H = 2160. A port whose topmost cabinet sits at Y = 540 keeps
    1 - 540/2160 = 0.75 of 659,722 = 494,791.5 -> floor 494,791."""
    got = _js(page, """
        return {
            top:  window.app.lowLatencyPortCapacity(659722, 0, 2160),
            q:    window.app.lowLatencyPortCapacity(659722, 540, 2160),
            half: window.app.lowLatencyPortCapacity(659722, 1080, 2160),
            past: window.app.lowLatencyPortCapacity(659722, 3000, 2160),
            noH:  window.app.lowLatencyPortCapacity(659722, 540, 0),
        };
    """)
    assert got['top'] == 659722
    assert got['q'] == 494791
    assert got['half'] == 329861
    assert got['past'] == 0
    assert got['noH'] == 659722


# ── half tiles ───────────────────────────────────────────────────────────

def test_half_tile_load_factor_is_0_65_and_a_quarter_would_be_0_325(page):
    got = _js(page, """
        const l = A.screen({ cabinet_width: 128, cabinet_height: 128 });
        const full = { width: 128, height: 128 };
        return {
            full:    window.app.getPanelLoadFactor(l, full),
            halfW:   window.app.getPanelLoadFactor(l, { width: 64, height: 128 }),
            halfH:   window.app.getPanelLoadFactor(l, { width: 128, height: 64 }),
            quarter: window.app.getPanelLoadFactor(l, { width: 64, height: 64 }),
        };
    """)
    assert got['full'] == 1
    assert abs(got['halfW'] - 0.65) < 1e-9
    assert abs(got['halfH'] - 0.65) < 1e-9
    assert abs(got['quarter'] - 0.325) < 1e-9


def test_half_tiles_carry_raw_pixel_area_into_data_capacity_not_the_1_3_factor(page):
    """Documenting, not asserting a bug: weight/watts use area x 1.3, data
    capacity uses raw area. A half tile is 0.65 cabinets of load but 0.5
    cabinets of bandwidth."""
    got = _js(page, """
        const l = A.screen({ cabinet_width: 128, cabinet_height: 128 });
        const half = { width: 64, height: 128 };
        return {
            factor: window.app.getPanelLoadFactor(l, half),
            pixels: window.app.getPanelPixelArea(half),
            fullPixels: window.app.getFullPanelPixels(l),
        };
    """)
    assert got['pixels'] / got['fullPixels'] == 0.5
    assert abs(got['factor'] - 0.65) < 1e-9


# ── frame rate / bit depth outside a processor's table ───────────────────

def test_frame_rate_above_a_processors_table_has_no_capacity(page):
    """FIXED (assertion flipped). This used to clamp to the LAST row:
    novastar-armor stops at 120 Hz, so 240 Hz handed back the 120 Hz figure -
    exactly twice the real 240 Hz capacity, so the port count came out half
    what the wall needs. The group settings dialog can produce that state,
    because processor, bit depth and frame rate are chosen independently from
    the members' distinct values with no check that the combination exists.

    Nothing is extrapolated to replace it: the manufacturer's published table
    is authoritative and no figure in this app is derived from a formula. An
    out-of-table frame rate therefore has NO capacity - 0, which the UI already
    renders as "N/A" pixels/port, ERROR panels/port and ERROR ports required.

    BELOW the table is a different case and still clamps, to the lowest
    published row: capacity runs as 1/frame rate, so that is less capacity than
    a slower frame rate really has (more ports, never fewer), and 23.976 Hz -
    offered in the frame rate list, below every table's 24 Hz first row - has
    no answer at all otherwise.
    """
    got = _js(page, """
        return {
            armor120: window.app.lookupPortCapacity(12, 120, 'novastar-armor'),
            armor240: window.app.lookupPortCapacity(12, 240, 'novastar-armor'),
            coex240:  window.app.lookupPortCapacity(12, 240, 'novastar-coex-1g'),
            coex250:  window.app.lookupPortCapacity(12, 250, 'novastar-coex-1g'),
            armor10:  window.app.lookupPortCapacity(12, 10, 'novastar-armor'),
            armor24:  window.app.lookupPortCapacity(12, 24, 'novastar-armor'),
            armorPorts: (() => {
                const s = A.screen({ id: 1, processorType: 'novastar-armor',
                                     bitDepth: 12, frameRate: 240 });
                return A.withProject([s], [], () => {
                    window.app.calculatePortAssignments(s);
                    return s._autoPortsRequired;
                });
            })(),
        };
    """)
    assert got['armor120'] == 164931
    # Armor publishes nothing past 120 Hz, so 240 Hz has no answer. It used to
    # report 164,931 - double the correct 82,465 the same bandwidth model gives.
    assert got['armor240'] == 0, got
    # COEX publishes 240 Hz, and stops there: 250 Hz is out of table for it.
    assert got['coex240'] == 82465
    assert got['coex250'] == 0, got
    # No capacity means no automatic port map either, rather than a plausible
    # one built on a figure the manufacturer never published.
    assert got['armorPorts'] == 0, got
    # Below the table still clamps to the lowest published row (the safe
    # direction), so 23.976 Hz keeps working.
    assert got['armor10'] == got['armor24'] == 824653, got


def test_group_settings_dialog_allows_a_processor_frame_rate_combination_that_does_not_exist(page):
    got = _js(page, """
        const a = A.screen({ id: 1, processorType: 'novastar-coex-1g',
                             bitDepth: 12, frameRate: 240 });
        const b = A.screen({ id: 2, processorType: 'novastar-armor',
                             bitDepth: 12, frameRate: 60 });
        const check = window.app.validateGroupSettings([a, b]);
        return {
            conflicts: check.conflicts,
            armorRates: window.app.getSupportedFrameRates('novastar-armor', 12),
        };
    """)
    assert 'processorType' in got['conflicts']
    assert 'frameRate' in got['conflicts']
    assert 240 in got['conflicts']['frameRate']
    assert 'novastar-armor' in got['conflicts']['processorType']
    assert 240 not in got['armorRates'], (
        'armor has no 240 Hz row, yet the dialog offers processor and frame '
        'rate as independent picks')


# ── power: I = P / (V x 1.73) ────────────────────────────────────────────

def test_group_amps_use_the_project_three_phase_formula(page):
    """4 cabinets x 200 W = 800 W at 208 V.
       1ph = 800 / 208            = 3.846 A
       3ph = 800 / (208 x 1.73)   = 2.223 A
    """
    got = _js(page, """
        const s = A.screen({ id: 1, panelWatts: 200, powerVoltage: 208 });
        const g = A.group([s]);
        return A.withProject([s], [g], () => window.app.getGroupTotals('g1'));
    """)
    assert got['watts'] == 800
    assert abs(got['amps1ph'] - 800 / 208) < 1e-9
    assert abs(got['amps3ph'] - 800 / (208 * 1.73)) < 1e-9


def test_a_mixed_voltage_group_refuses_to_blend_its_amps(page):
    got = _js(page, """
        const a = A.screen({ id: 1, powerVoltage: 110 });
        const b = A.screen({ id: 2, powerVoltage: 208, offset_x: 512 });
        const g = A.group([a, b]);
        return A.withProject([a, b], [g], () => window.app.getGroupTotals('g1'));
    """)
    assert got['voltageMismatch'] is True
    assert got['amps1ph'] is None
    assert got['amps3ph'] is None
    assert sorted(got['voltages']) == [110, 208]


def test_project_wide_power_totals_refuse_to_blend_mixed_voltages(page):
    """getPowerCounts (app-presets.js) feeds the on-canvas text-layer totals.

    FLIPPED. It used to sum watts across every screen and divide by whichever
    voltage it saw FIRST, so a 110 V screen beside a 208 V screen printed
    14.55 A 1ph / 8.41 A 3ph - one figure that belongs to neither wall. It now
    matches getGroupTotals: combined amps go null, the distinct voltages are
    listed, voltageMismatch is raised, and byVoltage carries the honest
    per-wall answers.
    """
    got = _js(page, """
        const a = A.screen({ id: 1, powerVoltage: 110, panelWatts: 200 });
        const b = A.screen({ id: 2, powerVoltage: 208, panelWatts: 200,
                             offset_x: 512 });
        return A.withProject([a, b], [], () => window.app.getPowerCounts());
    """)
    # 8 cabinets x 200 W = 1600 W total.
    assert got['totalWatts'] == 1600
    assert got['voltageMismatch'] is True
    assert got['voltage'] is None
    assert got['singlePhaseAmps'] is None
    assert got['threePhaseAmps'] is None
    assert sorted(got['voltages']) == [110, 208]
    # The honest answers, per wall: 800/110 = 7.27 A and 800/208 = 3.85 A.
    by_v = {b['voltage']: b for b in got['byVoltage']}
    assert sorted(by_v) == [110, 208]
    assert by_v[110]['watts'] == 800 and by_v[208]['watts'] == 800
    assert abs(by_v[110]['amps1ph'] - 800 / 110) < 1e-9
    assert abs(by_v[208]['amps1ph'] - 800 / 208) < 1e-9
    assert abs(by_v[110]['amps3ph'] - 800 / (110 * 1.73)) < 1e-9
    assert abs(by_v[208]['amps3ph'] - 800 / (208 * 1.73)) < 1e-9


def test_a_single_voltage_project_still_reports_combined_amps(page):
    """The mismatch rule must not touch the ordinary case: one voltage in the
    project still gets a real combined 1ph/3ph figure and no flag."""
    got = _js(page, """
        const a = A.screen({ id: 1, powerVoltage: 208, panelWatts: 200 });
        const b = A.screen({ id: 2, powerVoltage: 208, panelWatts: 200,
                             offset_x: 512 });
        return A.withProject([a, b], [], () => window.app.getPowerCounts());
    """)
    assert got['totalWatts'] == 1600
    assert got['voltageMismatch'] is False
    assert got['voltage'] == 208
    assert abs(got['singlePhaseAmps'] - 1600 / 208) < 1e-9
    assert abs(got['threePhaseAmps'] - 1600 / (208 * 1.73)) < 1e-9


def test_project_wide_circuit_total_is_the_real_map_not_a_bulk_division(page):
    """3 columns x 6 rows, 200 W a cabinet, 110 V / 20 A = 2200 W a circuit,
    Organized column-first.

    The map the app actually draws:  each column is 6 x 200 = 1200 W, two
    columns are 2400 W > 2200, so every column gets its own circuit = 3.
    getPowerCounts used to bulk-divide: ceil(18 x 200 / 2200) = 2. It now runs
    the real assignment (through getLayerCircuitsRequired, so a hand-drawn
    circuit map wins where there is one) and agrees.
    """
    got = _js(page, """
        const s = A.screen({
            id: 1, columns: 3, rows: 6, panelWatts: 200,
            powerVoltage: 110, powerAmperage: 20,
            powerFlowPattern: 'tl-v', powerOrganized: true, powerMaximize: false,
        });
        return A.withProject([s], [], () => ({
            bulk: window.app.getPowerCounts().circuits,
            real: window.app.calculatePowerAssignments(s).circuits.length,
        }));
    """)
    assert got['real'] == 3, got
    assert got['bulk'] == got['real'], (
        'the canvas text-layer circuit total (%d) is lower than the circuit map '
        'the app draws (%d)' % (got['bulk'], got['real']))


# ── ports: one implementation, or four? ──────────────────────────────────

def test_project_wide_port_total_honours_a_hand_drawn_port_map(page):
    """A screen wired by hand to 3 ports. getLayerPortsRequired - the one
    v0.11.0 collapsed the three copies into - says 3. getPortCounts, which
    feeds the on-canvas text layer, was a FOURTH copy: it re-ran the AUTOMATIC
    assignment and said 1, because 4 x 128 x 128 = 65,536 px fits one
    525,000 px Brompton port. It now routes through getLayerPortsRequired.
    """
    got = _js(page, """
        const s = A.screen({ id: 1, columns: 2, rows: 2, flowPattern: 'custom' });
        s.customPortPaths = {
            1: [{ row: 0, col: 0 }],
            2: [{ row: 0, col: 1 }],
            3: [{ row: 1, col: 0 }, { row: 1, col: 1 }],
        };
        s.customPortIndex = 3;
        return A.withProject([s], [], () => ({
            single: window.app.getLayerPortsRequired(s),
            project: window.app.getPortCounts().primary,
        }));
    """)
    assert got['single'] == 3
    assert got['project'] == got['single'], (
        'canvas text-layer port total says %d, the sidebar and the screen '
        'label say %d' % (got['project'], got['single']))


def test_project_wide_circuit_total_honours_a_hand_drawn_power_map(page):
    """The power twin of the ports test above: getPowerCounts had the same
    blind spot for powerCustomPaths. A 2x2 screen hand-wired to 3 circuits is
    3 circuits on the label, in the group roll-up and in the project total.
    Automatic assignment would have said 1 (4 x 200 W = 800 W on a
    110 x 20 = 2200 W circuit).
    """
    got = _js(page, """
        const s = A.screen({ id: 1, columns: 2, rows: 2, panelWatts: 200,
                             powerVoltage: 110, powerAmperage: 20,
                             powerFlowPattern: 'custom' });
        s.powerCustomPaths = {
            1: [{ row: 0, col: 0 }],
            2: [{ row: 0, col: 1 }],
            3: [{ row: 1, col: 0 }, { row: 1, col: 1 }],
        };
        s.powerCustomIndex = 3;
        return A.withProject([s], [], () => ({
            single: window.app.getLayerCircuitsRequired(
                s, window.app.calculatePowerAssignments(s).circuits.length),
            auto: window.app.calculatePowerAssignments(s).circuits.length,
            project: window.app.getPowerCounts().circuits,
        }));
    """)
    assert got['auto'] == 1, got
    assert got['single'] == 3
    assert got['project'] == got['single'], (
        'canvas text-layer circuit total says %d, the screen label says %d'
        % (got['project'], got['single']))


def test_a_port_that_crosses_members_is_not_counted_twice_project_wide(page):
    """One cable drawn from Upper across onto Lower: the wall is 1 port, and
    the project total must say 1, not 2. Summing getLayerPortsRequired gets
    this right because that function returns 0 for a member fed by a peer."""
    got = _js(page, """
        const up = A.screen({ id: 1, name: 'Upper', columns: 2, rows: 2,
                              flowPattern: 'custom' });
        const lo = A.screen({ id: 2, name: 'Lower', columns: 2, rows: 2,
                              offset_y: 256, flowPattern: 'custom' });
        up.customPortPaths = {
            1: [{ row: 0, col: 0 }, { row: 0, col: 1 },
                { row: 1, col: 0 }, { row: 1, col: 1 },
                { layerId: 2, row: 0, col: 0 }, { layerId: 2, row: 0, col: 1 },
                { layerId: 2, row: 1, col: 0 }, { layerId: 2, row: 1, col: 1 }],
        };
        lo.customPortPaths = {};
        const g = A.group([up, lo]);
        return A.withProject([up, lo], [g], () => ({
            group: window.app.getGroupTotals('g1').portsPrimary,
            project: window.app.getPortCounts().primary,
        }));
    """)
    assert got['group'] == 1
    assert got['project'] == got['group']


def test_sidebar_label_and_group_rollup_agree_on_a_port_that_crosses_members(page):
    """One cable drawn from Upper across onto Lower. Upper owns port 1 and
    every one of Lower's cabinets hangs off it, so the wall is 1 port."""
    got = _js(page, """
        const up = A.screen({ id: 1, name: 'Upper', columns: 2, rows: 2,
                              flowPattern: 'custom' });
        const lo = A.screen({ id: 2, name: 'Lower', columns: 2, rows: 2,
                              offset_y: 256, flowPattern: 'custom' });
        up.customPortPaths = {
            1: [{ row: 0, col: 0 }, { row: 0, col: 1 },
                { row: 1, col: 0 }, { row: 1, col: 1 },
                { layerId: 2, row: 0, col: 0 }, { layerId: 2, row: 0, col: 1 },
                { layerId: 2, row: 1, col: 0 }, { layerId: 2, row: 1, col: 1 }],
        };
        lo.customPortPaths = {};
        const g = A.group([up, lo]);
        return A.withProject([up, lo], [g], () => ({
            upper: window.app.getLayerPortsRequired(up),
            lower: window.app.getLayerPortsRequired(lo),
            group: window.app.getGroupTotals('g1').portsPrimary,
        }));
    """)
    assert got['upper'] == 1
    assert got['lower'] == 0
    assert got['group'] == 1


def test_partial_coverage_by_a_peer_still_counts_the_uncovered_cabinets(page):
    """FIXED (assertion was already written for the fixed behaviour). Lower is
    a 2 x 20 wall. Upper's port picks up ONE of its 40 cabinets. Lower used to
    report 0 ports - the served-by-a-peer test was a bare `.some()` - so the
    other 39 cabinets were planned for with no port at all.

    Only FULL coverage returns 0 now. Partial coverage falls through to the
    member's own requirement, which is a true upper bound on what the uncovered
    cabinets need (removing cabinets can never make the automatic walk need
    more ports). Over-counting by at most the covered share is the safe
    direction; silently zeroing is not.
    """
    got = _js(page, """
        const up = A.screen({ id: 1, name: 'Upper', columns: 2, rows: 2,
                              flowPattern: 'custom' });
        const lo = A.screen({ id: 2, name: 'Lower', columns: 20, rows: 2,
                              offset_y: 256, flowPattern: 'custom',
                              processorType: 'brompton', bitDepth: 8,
                              frameRate: 60 });
        up.customPortPaths = { 1: [{ row: 0, col: 0 },
                                   { layerId: 2, row: 0, col: 0 }] };
        lo.customPortPaths = {};
        const g = A.group([up, lo]);
        return A.withProject([up, lo], [g], () => {
            window.app.calculatePortAssignments(lo);
            return {
                lowerPorts: window.app.getLayerPortsRequired(lo),
                lowerAuto: lo._autoPortsRequired,
                lowerCabinets: lo.panels.length,
                group: window.app.getGroupTotals('g1').portsPrimary,
            };
        });
    """)
    assert got['lowerCabinets'] == 40
    # 40 x 128 x 128 = 655,360 px against a 525,000 px Brompton port -> 2 ports.
    assert got['lowerAuto'] == 2, got
    assert got['lowerPorts'] > 0, (
        'Lower has %d cabinets and needs %d ports, but one cabinet picked up '
        'by a peer zeroes the whole member' % (got['lowerCabinets'], got['lowerAuto']))


# ── group roll-ups ───────────────────────────────────────────────────────

def test_per_cabinet_weight_and_watts_never_cross_between_members(page):
    """1 m section: 18 cabinets x 20 kg / 300 W.
       0.5 m section: 80 cabinets x 6 kg / 90 W.
       Weight = 18x20 + 80x6 = 360 + 480 = 840 kg.
       Watts  = 18x300 + 80x90 = 5400 + 7200 = 12,600 W.
    Neither figure is reachable by applying one member's per-cabinet number to
    the other's cabinets (which would give 1960 kg / 29,400 W or 588 kg /
    8,820 W).
    """
    got = _js(page, """
        const big = A.screen({ id: 1, columns: 6, rows: 3,
                               cabinet_width: 128, cabinet_height: 128,
                               panel_weight: 20, panelWatts: 300,
                               powerVoltage: 208 });
        const small = A.screen({ id: 2, columns: 10, rows: 8,
                                 cabinet_width: 64, cabinet_height: 64,
                                 panel_weight: 6, panelWatts: 90,
                                 offset_y: 384, powerVoltage: 208 });
        const g = A.group([big, small]);
        return A.withProject([big, small], [g], () => window.app.getGroupTotals('g1'));
    """)
    assert got['cabinets'] == 18 + 80
    assert abs(got['weightKg'] - 840) < 1e-6
    assert abs(got['watts'] - 12600) < 1e-6
    assert abs(got['weightLb'] - 840 * 2.20462) < 1e-6
    assert abs(got['amps3ph'] - 12600 / (208 * 1.73)) < 1e-9


def test_group_totals_derate_half_tiles_in_weight_and_watts(page):
    """4 cabinets, two of them half-width. Equivalent cabinets = 2 x 1 +
    2 x 0.65 = 3.3. Weight = 3.3 x 20 = 66 kg. Watts = 3.3 x 200 = 660 W.
    Cabinet COUNT is still 4 - a half cabinet is a cabinet on the truck."""
    got = _js(page, """
        const s = A.screen({ id: 1, columns: 2, rows: 2 });
        s.panels[2].width = 64; s.panels[2].halfTile = 'width';
        s.panels[3].width = 64; s.panels[3].halfTile = 'width';
        const g = A.group([s]);
        return A.withProject([s], [g], () => window.app.getGroupTotals('g1'));
    """)
    assert abs(got['equivalentPanels'] - 3.3) < 1e-9
    assert abs(got['weightKg'] - 66) < 1e-9
    assert abs(got['watts'] - 660) < 1e-9
    assert got['cabinets'] == 4
    # pixels are raw area: 2 x 16384 + 2 x 8192 = 49,152
    assert got['pixels'] == 2 * 128 * 128 + 2 * 64 * 128


def test_blank_cabinets_are_a_hole_in_the_wall_everywhere_it_is_read(page):
    """FIXED. A blank cabinet is a hole in the wall - no cabinet hangs there,
    it has no weight and it draws nothing. The group roll-up and getPowerCounts
    always dropped it; updatePowerCapacityDisplay (the Power sidebar) counted
    it, so a 2 x 2 screen with one blank read 800 W in the sidebar and 600 W in
    the group - GROUPING A SCREEN CHANGED ITS WATTAGE.

    Driven through the real function and read off the figures it stamps on the
    layer (_powerTotalAmps1 / _powerTotalAmps3), not off a re-implementation of
    its filter and not off any element style.
    """
    got = _js(page, """
        const s = A.screen({ id: 1, columns: 2, rows: 2, panelWatts: 200,
                             powerVoltage: 110 });
        s.panels[3].blank = true;
        const g = A.group([s]);
        return A.withProject([s], [g], () => {
            const rollup = window.app.getGroupTotals('g1');
            const savedLayer = window.app.currentLayer;
            window.app.currentLayer = s;
            try { window.app.updatePowerCapacityDisplay(); }
            finally { window.app.currentLayer = savedLayer; }
            return {
                groupWatts: rollup.watts,
                groupAmps1: rollup.amps1ph,
                groupAmps3: rollup.amps3ph,
                // watts = amps x volts, so the stamped amps ARE the wattage
                // the sidebar just displayed.
                sidebarWatts: s._powerTotalAmps1 * 110,
                sidebarAmps1: s._powerTotalAmps1,
                sidebarAmps3: s._powerTotalAmps3,
            };
        });
    """)
    assert got['groupWatts'] == 600      # 3 real cabinets
    assert abs(got['sidebarWatts'] - got['groupWatts']) < 1e-9, (
        'sidebar/canvas report %g W, the group roll-up reports %g W for the '
        'same screen' % (got['sidebarWatts'], got['groupWatts']))
    # I = P / V and I = P / (V x 1.73), on the same 600 W.
    assert abs(got['sidebarAmps1'] - 600 / 110) < 1e-9, got
    assert abs(got['sidebarAmps3'] - 600 / (110 * 1.73)) < 1e-9, got
    assert abs(got['sidebarAmps1'] - got['groupAmps1']) < 1e-9, got
    assert abs(got['sidebarAmps3'] - got['groupAmps3']) < 1e-9, got


def test_a_screen_with_no_panelWatts_reports_the_same_thing_everywhere(page):
    """FLIPPED. getPowerCounts used to substitute 200 W a cabinet where
    panelWatts was unset, so the same wall was 0 W / 0 circuits on its own
    label and 800 W / 1 circuit in the project total.

    getPowerCounts now reads parseFloat(...) || 0, which is what every other
    reader in the app does - getGroupTotals, calculatePowerAssignments,
    updatePowerCapacityDisplay and the canvas power label. That rule is forced
    by the circuit fix above: circuits now come from calculatePowerAssignments,
    which bails at panelWatts <= 0, so a 200 W stand-in would print 800 W
    against 0 circuits - less coherent than what it replaced.

    The zero is not silently confident: getPowerCounts lists the screen in
    `wattsUnset` so the caller can print "not entered" rather than "0 A".
    """
    got = _js(page, """
        const s = A.screen({ id: 1, powerVoltage: 110, powerAmperage: 20 });
        delete s.panelWatts;
        const g = A.group([s]);
        return A.withProject([s], [g], () => ({
            groupWatts: window.app.getGroupTotals('g1').watts,
            groupCircuits: window.app.getGroupTotals('g1').circuits,
            groupUnset: window.app.getGroupTotals('g1').wattsUnset,
            projectWatts: window.app.getPowerCounts().totalWatts,
            projectCircuits: window.app.getPowerCounts().circuits,
            unset: window.app.getPowerCounts().wattsUnset,
        }));
    """)
    assert got['projectWatts'] == 0        # no stand-in wattage is invented
    assert got['unset'] == [1], 'the screen with no wattage must be flagged'
    assert got['groupUnset'] == [1], (
        'the group roll-up must flag the same screen, or a 0 W group row reads '
        'as a wall that draws nothing')
    assert got['groupWatts'] == got['projectWatts'], (
        'group roll-up says %g W / %d circuits, project total says %g W / %d '
        'circuits for the same screen'
        % (got['groupWatts'], got['groupCircuits'],
           got['projectWatts'], got['projectCircuits']))
    assert got['groupCircuits'] == got['projectCircuits']


def test_group_creation_does_not_make_members_agree_on_low_latency(page):
    """lowLatency is in GROUP_SHARED_LAYER_FIELDS (propagated on EDIT) but not
    in GROUP_SHARED_SETTINGS (validated at creation), so a group can hold a
    Brompton member at 262,500 px/port beside one at 525,000. A port drawn from
    the 525,000 member across into the other is judged at 525,000."""
    got = _js(page, """
        const a = A.screen({ id: 1, processorType: 'brompton', lowLatency: true });
        const b = A.screen({ id: 2, processorType: 'brompton', lowLatency: false,
                             offset_y: 256 });
        return {
            conflicts: Object.keys(window.app.validateGroupSettings([a, b]).conflicts),
            capA: window.app.calculatePortCapacity(8, 60, 'brompton', true),
            capB: window.app.calculatePortCapacity(8, 60, 'brompton', false),
        };
    """)
    assert got['capA'] == 262500 and got['capB'] == 525000
    assert 'lowLatency' in got['conflicts'], (
        'grouping two Brompton screens with different Low Latency raised no '
        'conflict, yet their pixels/port differ 2:1 (%d vs %d)'
        % (got['capA'], got['capB']))


def test_hidden_members_and_non_screens_are_skipped_not_silently_summed(page):
    got = _js(page, """
        const a = A.screen({ id: 1 });
        const b = A.screen({ id: 2, offset_x: 256 });  b.visible = false;
        const c = A.screen({ id: 3, offset_x: 512 });  c.type = 'image';
        const g = A.group([a, b, c]);
        return A.withProject([a, b, c], [g], () => window.app.getGroupTotals('g1'));
    """)
    assert got['memberCount'] == 1
    assert got['hiddenCount'] == 1
    assert got['nonScreenCount'] == 1
    assert got['cabinets'] == 4


def test_a_layer_with_no_visible_key_still_counts(page):
    got = _js(page, """
        const a = A.screen({ id: 1 });
        delete a.visible;
        const b = A.screen({ id: 2, offset_x: 256 });
        const g = A.group([a, b]);
        return A.withProject([a, b], [g], () => window.app.getGroupTotals('g1'));
    """)
    assert got['memberCount'] == 2
    assert got['cabinets'] == 8
