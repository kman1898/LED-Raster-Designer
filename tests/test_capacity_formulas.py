"""Data-capacity audit fixes: formula rates, oversized cabinets in Max
Capacity, the exact Low Latency derate, drawn port numbers in the .scr, and
legacy blank cabinets.

1. A frame rate between two published rows used to be INTERPOLATED. Capacity
   runs as 1 / frame rate, so a straight line between two rows always sits
   above the curve: Armor 8-bit 72 Hz read 593,749 where the formula gives
   floor(0.95e9 / (24 x 72)) = 549,768 (+8%). Formula-derived tables (Armor,
   COEX 1G, Brompton and its ULL half) now give the exact floored formula;
   published-only tables (5G, HELIOS) give the nearest published row AT OR
   ABOVE the rate, and nothing past the last row. JS and Python agree.
2. Max Capacity on a pixel-sum processor (COEX 1G, Brompton, HELIOS) put a
   cabinet bigger than a port on a port of its own and reported an ordinary
   count. It is the same ERROR the Organized mode and Armor already give.
3. The NovaStar Low Latency derate floor((1 - Y/H) x cap) lost a pixel to
   floating point; it is floor((H - Y) x cap / H) in integers now.
4. The .scr exporter renumbered drawn ports by position (drawn 1 and 4 ->
   1 and 2) and ignored per-run overrides when numbering the automatic walk.
5. A legacy `blank: true` cabinet (hidden false) counted as load in the data
   walk. The owner's ruling: a blank does not exist - it carries no pixels
   and takes no port, exactly like hidden.

Run locally:
    python -m pytest tests/test_capacity_formulas.py -v --browser chromium
"""

import math
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import scr_project  # noqa: E402
from scr_project import (  # noqa: E402
    PORT_CAPACITY_TABLES, Warnings, assignments_for_layer,
    calculate_port_assignments, low_latency_port_capacity, lookup_port_capacity)

APP_CORE = os.path.join(
    os.path.dirname(__file__), '..', 'src', 'static', 'js', 'app-core.js')

# The formulas the formula-derived tables were built from, stated here
# independently of the app (test_audit_numbers.py derives the same ones).
FORMULAS = {
    'novastar-armor': lambda bd, fr: 950000000 // ({8: 24, 10: 48, 12: 48}[bd] * fr),
    'novastar-coex-1g': lambda bd, fr: 950000000 // ({8: 24, 10: 32, 12: 48}[bd] * fr),
    'brompton': lambda bd, fr: {8: 31500000, 10: 25200000, 12: 21000000}[bd] // fr,
    'brompton-ull': lambda bd, fr: {8: 31500000, 10: 25200000, 12: 21000000}[bd] // (2 * fr),
}
PUBLISHED_ONLY = ('novastar-5g', 'megapixel-1g', 'megapixel-2.5g')

# Every rate the UI can hold, plus a few no list offers.
RATES = [23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60, 72, 100, 120, 144, 150,
         180, 192, 200, 240, 250, 10, 60.4, 119.88, 300]


def _parse_js_tables():
    src = open(APP_CORE, encoding='utf-8').read()
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
        tables[m.group(1)] = {
            int(bm.group(1)): {int(a): int(b) for a, b in
                               re.findall(r'(\d+)\s*:\s*(\d+)', bm.group(2))}
            for bm in re.finditer(r'(\d+):\s*\{([^}]*)\}', m.group(2))}
    return tables


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# ── 1. formula rates, Python side ────────────────────────────────────────

def test_the_python_tables_are_the_js_tables():
    assert PORT_CAPACITY_TABLES == _parse_js_tables()


def test_every_formula_table_row_is_the_floored_formula_exactly():
    """The formula may only fill the gaps if it IS the table at every row."""
    bad = []
    for proc, f in FORMULAS.items():
        for bd, row in PORT_CAPACITY_TABLES[proc].items():
            for fr, cap in row.items():
                if cap != f(bd, fr):
                    bad.append('%s %d-bit %d Hz: table %d, formula %d'
                               % (proc, bd, fr, cap, f(bd, fr)))
                if scr_project.formula_port_capacity(proc, bd, fr) != cap:
                    bad.append('%s %d-bit %d Hz: app formula disagrees' % (proc, bd, fr))
    assert not bad, '\n'.join(bad)


def _expected(proc, bd, rate):
    """The rule, re-stated from the ruling rather than from the code."""
    row = PORT_CAPACITY_TABLES[proc][bd]
    rates = sorted(row)
    if rate <= rates[0]:
        return row[rates[0]]
    if rate > rates[-1]:
        return 0
    if proc in FORMULAS:
        return FORMULAS[proc](bd, math.ceil(rate))
    return row[min(r for r in rates if r >= rate)]


def test_python_lookup_follows_the_rule_at_every_rate():
    bad = []
    for proc, table in PORT_CAPACITY_TABLES.items():
        for bd in table:
            for rate in RATES:
                got = lookup_port_capacity(bd, rate, proc)
                want = _expected(proc, bd, rate)
                if got != want:
                    bad.append('%s %d-bit @ %s: got %d, want %d' % (proc, bd, rate, got, want))
    assert not bad, '\n'.join(bad)


def test_the_audit_cases_in_python():
    # Armor 8-bit 72 Hz: the formula, not the interpolated 593,749.
    assert lookup_port_capacity(8, 72, 'novastar-armor') == 549768
    assert lookup_port_capacity(10, 72, 'novastar-armor') == 274884
    # 5G publishes no 100 Hz row: the 120 Hz row, never 1,967,466.
    assert lookup_port_capacity(8, 100, 'novastar-5g') == 1475600
    # The drop-frame rates still read the published row they round up to.
    assert lookup_port_capacity(8, 59.94, 'novastar-armor') == 659722
    assert lookup_port_capacity(8, 59.94, 'novastar-5g') == 2951200
    # Past the last published row: unknown, not a guess.
    assert lookup_port_capacity(8, 250, 'novastar-5g') == 0
    assert lookup_port_capacity(10, 250, 'megapixel-1g') == 0
    assert lookup_port_capacity(8, 144, 'novastar-armor') == 0


def test_no_formula_figure_is_ever_above_the_curve():
    """Every answer between rows is at or below the true formula figure at the
    requested rate - the direction that adds ports, never removes them."""
    budgets = {'novastar-armor': (950000000, {8: 24, 10: 48, 12: 48}),
               'novastar-coex-1g': (950000000, {8: 24, 10: 32, 12: 48}),
               'brompton': (None, {8: 1, 10: 1, 12: 1}),
               'brompton-ull': (None, {8: 2, 10: 2, 12: 2})}
    brompton = {8: 31500000, 10: 25200000, 12: 21000000}
    for proc, (budget, per_pixel) in budgets.items():
        for bd in PORT_CAPACITY_TABLES[proc]:
            for rate in (61, 72, 99.5, 100, 119.88, 130, 199):
                got = lookup_port_capacity(bd, rate, proc)
                true = (budget or brompton[bd]) / (per_pixel[bd] * rate)
                assert got <= true, (proc, bd, rate, got, true)


# ── 3. the Low Latency derate, Python side ───────────────────────────────

def test_python_low_latency_derate_is_exact():
    assert low_latency_port_capacity(1649305, 576, 720) == 329861
    assert low_latency_port_capacity(1649305, 576.0, 720.0) == 329861
    assert low_latency_port_capacity(1649305, 0, 720) == 1649305
    assert low_latency_port_capacity(1649305, 720, 720) == 0
    assert low_latency_port_capacity(1649305, 576, 0) == 1649305
    for h in (720, 1080, 2160):
        for y in range(0, h, 37):
            assert low_latency_port_capacity(1649305, y, h) == (h - y) * 1649305 // h


# ── shared builders for the walk ─────────────────────────────────────────

def _layer(cols, rows, cw=128, ch=128, blank=(), hidden=(), **extra):
    panels = []
    for r in range(rows):
        for c in range(cols):
            panels.append({'id': r * cols + c + 1, 'row': r, 'col': c,
                           'x': c * cw, 'y': r * ch, 'width': cw, 'height': ch,
                           'hidden': (c, r) in hidden, 'blank': (c, r) in blank,
                           'halfTile': 'none'})
    layer = {'id': 1, 'name': 'S', 'type': 'screen', 'columns': cols, 'rows': rows,
             'cabinet_width': cw, 'cabinet_height': ch,
             'processorType': 'brompton', 'bitDepth': 8, 'frameRate': 60,
             'flowPattern': 'tl-h', 'portMappingMode': 'organized',
             'lowLatency': False, 'panels': panels}
    layer.update(extra)
    return layer


def _ports(assignments):
    return sorted({a['port'] for a in assignments})


# ── 2. an oversized cabinet in Max Capacity, Python side ─────────────────

@pytest.mark.parametrize('proc,bd,fr', [
    ('brompton', 12, 240),          # 87,500 px against a 131,072 px cabinet
    ('novastar-coex-1g', 12, 240),  # 82,465
    ('megapixel-1g', 12, 240),      # 87,000
])
def test_python_max_capacity_oversized_cabinet_is_an_error(proc, bd, fr):
    warnings = Warnings()
    layer = _layer(4, 2, cw=256, ch=512, processorType=proc, bitDepth=bd,
                   frameRate=fr, portMappingMode='max')
    assert calculate_port_assignments(layer, 2160, warnings) == []
    assert any('does not fit on a port' in w for w in warnings.items), warnings.items
    # Organized already said so; the two modes agree now.
    layer['portMappingMode'] = 'organized'
    assert calculate_port_assignments(layer, 2160, Warnings()) == []


def test_python_max_capacity_still_maps_a_cabinet_that_fits():
    layer = _layer(4, 2, cw=256, ch=256, bitDepth=12, frameRate=240,
                   portMappingMode='max')  # 65,536 px each on 87,500
    assert _ports(calculate_port_assignments(layer, 2160)) == list(range(1, 9))


# ── 4. the .scr exporter's port numbers ──────────────────────────────────

def test_drawn_ports_keep_their_drawn_numbers():
    layer = _layer(4, 2, flowPattern='custom', customPortPaths={
        '1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}],
        '4': [{'row': 1, 'col': 0}, {'row': 1, 'col': 1}],
    })
    got = assignments_for_layer(layer, 2160, Warnings())
    assert _ports(got) == [1, 4]
    by_cell = {(a['panel']['row'], a['panel']['col']): a['port'] for a in got}
    assert by_cell[(1, 0)] == by_cell[(1, 1)] == 4


def test_a_key_that_names_no_port_goes_after_the_highest_and_warns():
    warnings = Warnings()
    layer = _layer(4, 2, flowPattern='custom', customPortPaths={
        '3': [{'row': 0, 'col': 0}], 'x': [{'row': 1, 'col': 0}]})
    got = assignments_for_layer(layer, 2160, warnings)
    assert _ports(got) == [3, 4]
    assert any("'x'" in w for w in warnings.items), warnings.items


def test_the_auto_walk_skips_overridden_numbers_and_keeps_the_override():
    """Brompton 8-bit 60 Hz = 32 cabinets of 128 x 128 per port. Port 1 of
    a 16 x 4 wall taken over and redrawn along row 3: the Max Capacity walk
    lays over the other 48 cabinets and numbers its two ports 2 and 3."""
    layer = _layer(16, 4, portMappingMode='max',
                   customPortOverrides=[1],
                   customPortPaths={'1': [{'row': 3, 'col': c} for c in range(16)]})
    got = calculate_port_assignments(layer, 2160)
    assert _ports(got) == [1, 2, 3]
    override = [a for a in got if a['port'] == 1]
    assert [(a['panel']['row'], a['panel']['col']) for a in override] == \
        [(3, c) for c in range(16)]
    # Every cabinet once, and none of the overridden ones on the walk's ports.
    cells = [(a['panel']['row'], a['panel']['col']) for a in got]
    assert len(cells) == len(set(cells)) == 64
    assert all(a['panel']['row'] != 3 for a in got if a['port'] != 1)


def test_an_empty_override_still_reserves_its_number():
    layer = _layer(16, 2, portMappingMode='max', customPortOverrides=[1],
                   customPortPaths={})
    assert _ports(calculate_port_assignments(layer, 2160)) == [2]


# ── 5. legacy blanks, Python side ────────────────────────────────────────

def _ninety_blanks(**extra):
    """15 x 12 = 180 cabinets of 128 x 128 on Brompton 8-bit 60 Hz (32 per
    port), half of them legacy blanks (blank true, hidden false) in a
    checkerboard: 90 real cabinets, 3 ports. Counting the blanks gave 6."""
    blanks = {(c, r) for r in range(12) for c in range(15) if (c + r) % 2}
    assert len(blanks) == 90
    extra.setdefault('portMappingMode', 'max')
    return _layer(15, 12, blank=blanks, **extra)


def test_python_ninety_legacy_blanks_do_not_double_the_ports():
    layer = _ninety_blanks()
    got = calculate_port_assignments(layer, 2160)
    assert _ports(got) == [1, 2, 3]
    assert not any(a['panel']['blank'] for a in got)


def test_python_blank_is_treated_exactly_like_hidden():
    for mode in ('max', 'organized'):
        for proc in ('brompton', 'novastar-armor', 'novastar-5g'):
            a = _ninety_blanks(portMappingMode=mode, processorType=proc)
            b = _ninety_blanks(portMappingMode=mode, processorType=proc)
            for p in b['panels']:
                p['hidden'], p['blank'] = p['blank'], False
            pa = [(x['panel']['id'], x['port']) for x in calculate_port_assignments(a, 2160)]
            pb = [(x['panel']['id'], x['port']) for x in calculate_port_assignments(b, 2160)]
            assert pa == pb, (mode, proc)


# ── Part 2: the app itself ───────────────────────────────────────────────

@pytest.fixture(scope='module')
def page(e2e_server, pw_browser):
    pytest.importorskip('playwright.sync_api', reason='playwright not installed')
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function('() => window.app && window.app.portCapacityTables')
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


HELPERS_JS = """
window.__cap = {
    screen(o) {
        o = Object.assign({
            id: 9101, name: 'S', type: 'screen', visible: true,
            columns: 2, rows: 2, cabinet_width: 128, cabinet_height: 128,
            offset_x: 0, offset_y: 0, canvas_id: 'c1',
            processorType: 'brompton', bitDepth: 8, frameRate: 60,
            lowLatency: false, flowPattern: 'tl-h', portMappingMode: 'organized',
            group_id: null, blanks: [],
        }, o || {});
        const panels = [];
        let n = 1;
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                const blank = o.blanks.some(b => b[0] === c && b[1] === r);
                panels.push({ id: n, number: n, row: r, col: c,
                    x: o.offset_x + c * o.cabinet_width,
                    y: o.offset_y + r * o.cabinet_height,
                    width: o.cabinet_width, height: o.cabinet_height,
                    hidden: false, blank, halfTile: 'none' });
                n++;
            }
        }
        delete o.blanks;
        o.panels = panels;
        return o;
    },
    withProject(layers, fn) {
        const app = window.app;
        const saved = { project: app.project, current: app.currentLayer };
        app.project = { layers, groups: [],
            canvases: [{ id: 'c1', name: 'C1', raster_width: 4096, raster_height: 2160 }],
            raster_width: 4096, raster_height: 2160 };
        try { return fn(); } finally {
            app.project = saved.project;
            app.currentLayer = saved.current;
        }
    },
    ninetyBlanks(extra) {
        const blanks = [];
        for (let r = 0; r < 12; r++) for (let c = 0; c < 15; c++) {
            if ((c + r) % 2) blanks.push([c, r]);
        }
        return this.screen(Object.assign({ columns: 15, rows: 12, blanks,
                                           portMappingMode: 'max' }, extra || {}));
    },
};
"""


def _js(page, body, arg=None):
    return page.evaluate('(arg) => { const C = window.__cap; %s }' % body, arg)


def test_js_lookup_matches_python_at_every_rate(page):
    """One rule, two implementations: every processor, depth and rate."""
    cases = [(proc, bd, rate) for proc, table in PORT_CAPACITY_TABLES.items()
             for bd in table for rate in RATES]
    got = _js(page, """
        return arg.map(([p, b, r]) => window.app.lookupPortCapacity(b, r, p));
    """, cases)
    bad = ['%s %d-bit @ %s: js %d, python %d' % (p, b, r, j, lookup_port_capacity(b, r, p))
           for (p, b, r), j in zip(cases, got) if j != lookup_port_capacity(b, r, p)]
    assert not bad, '\n'.join(bad)
    bad = ['%s %d-bit @ %s: js %d, rule %d' % (p, b, r, j, _expected(p, b, r))
           for (p, b, r), j in zip(cases, got) if j != _expected(p, b, r)]
    assert not bad, '\n'.join(bad)


def test_the_audit_cases_in_the_app(page):
    got = _js(page, """
        const a = window.app;
        return {
            armor72: a.lookupPortCapacity(8, 72, 'novastar-armor'),
            g5_100: a.lookupPortCapacity(8, 100, 'novastar-5g'),
            g5_250: a.lookupPortCapacity(8, 250, 'novastar-5g'),
            ull72: a.calculatePortCapacity(12, 72, 'brompton', true),
            coex100: a.lookupPortCapacity(10, 100, 'novastar-coex-1g'),
        };
    """)
    assert got == {'armor72': 549768, 'g5_100': 1475600, 'g5_250': 0,
                   'ull72': 145833, 'coex100': 296875}, got


def test_an_unselected_72hz_armor_screen_is_walked_on_the_formula(page):
    """The figure reaches the port walk of a layer nobody selected: 8-bit
    72 Hz Armor holds 549,768 px, so a row of 128 x 128 cabinets goes 33 to a
    port in Max Capacity, not the 36 the interpolated 593,749 allowed."""
    got = _js(page, """
        const s = C.screen({ processorType: 'novastar-armor', frameRate: 72,
                             columns: 36, rows: 2, portMappingMode: 'max' });
        return C.withProject([s], () => {
            const items = window.app.calculatePortAssignments(s);
            return items.filter(i => i.port === 1).length;
        });
    """)
    assert got == 33, got


def test_js_low_latency_derate_is_exact(page):
    got = _js(page, """
        const a = window.app;
        const out = [a.lowLatencyPortCapacity(1649305, 576, 720)];
        for (const h of [720, 1080, 2160]) {
            for (let y = 0; y < h; y += 37) {
                out.push([h, y, a.lowLatencyPortCapacity(1649305, y, h)]);
            }
        }
        return out;
    """)
    assert got[0] == 329861
    bad = [(h, y, v) for h, y, v in got[1:] if v != (h - y) * 1649305 // h]
    assert not bad, bad[:5]


@pytest.mark.parametrize('proc', ['brompton', 'novastar-coex-1g', 'megapixel-1g'])
def test_max_capacity_oversized_cabinet_reads_error_in_the_sidebar(page, proc):
    """Brompton 12-bit 240 Hz is 87,500 px; a 256 x 512 cabinet is 131,072.
    It used to read 8 ports at 150%, no error."""
    got = _js(page, """
        const s = C.screen({ processorType: arg, bitDepth: 12, frameRate: 240,
                             columns: 4, rows: 2, cabinet_width: 256,
                             cabinet_height: 512, portMappingMode: 'max' });
        return C.withProject([s], () => {
            const app = window.app;
            const items = app.calculatePortAssignments(s);
            app.currentLayer = s;
            app.updatePortCapacityDisplay();
            return { items: items.length, error: !!s._capacityError,
                     sidebar: document.getElementById('ports-required').textContent };
        });
    """, proc)
    assert got == {'items': 0, 'error': True, 'sidebar': 'ERROR'}, got


def test_ninety_legacy_blanks_do_not_turn_three_ports_into_six(page):
    got = _js(page, """
        const s = C.ninetyBlanks();
        return C.withProject([s], () => {
            const app = window.app;
            const items = app.calculatePortAssignments(s);
            app.currentLayer = s;
            app.updatePortCapacityDisplay();
            const port1 = items.filter(i => i.port === 1).map(i => i.panel);
            const withBlank = port1.concat([s.panels.find(p => p.blank)]);
            const r = window.canvasRenderer;
            return {
                ports: new Set(items.map(i => i.port)).size,
                blanksCarried: items.filter(i => i.panel.blank).length,
                sidebar: document.getElementById('ports-required').textContent,
                loadSame: r.getPortPixelLoad(s, port1) === r.getPortPixelLoad(s, withBlank),
            };
        });
    """)
    assert got == {'ports': 3, 'blanksCarried': 0, 'sidebar': '3', 'loadSame': True}, got


@pytest.mark.parametrize('proc', ['brompton', 'novastar-armor', 'novastar-5g'])
@pytest.mark.parametrize('mode', ['max', 'organized'])
def test_a_legacy_blank_walks_exactly_like_hidden(page, proc, mode):
    got = _js(page, """
        const [proc, mode] = arg;
        const a = C.ninetyBlanks({ processorType: proc, portMappingMode: mode });
        const b = C.ninetyBlanks({ id: 9102, processorType: proc, portMappingMode: mode });
        b.panels.forEach(p => { p.hidden = p.blank; p.blank = false; });
        const walk = (s) => C.withProject([s], () => window.app
            .calculatePortAssignments(s).map(i => [i.panel.id, i.port]));
        return { blank: walk(a), hidden: walk(b) };
    """, [proc, mode])
    assert got['blank'] == got['hidden']


def test_the_js_walk_matches_the_python_walk_on_blanks(page):
    js = _js(page, """
        const s = C.ninetyBlanks();
        return C.withProject([s], () => window.app
            .calculatePortAssignments(s).map(i => [i.panel.id, i.port]));
    """)
    py = [[a['panel']['id'], a['port']]
          for a in calculate_port_assignments(_ninety_blanks(), 2160)]
    assert js == py
