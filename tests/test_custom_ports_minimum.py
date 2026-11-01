"""Ports required is the fewest ports a screen needs, and Organized splits
a row too long for one port.

Two owner rulings (Matt, 2026-11-01), on a 90 x 5 wall of 192 x 384
cabinets on NovaStar Legacy (Armor), 659,722 px a port, 8 cabinets wide a
port:

* "ports required should be in the current setting as in organized or max
  this is the minimum amount of ports needed under ideal circumstances".
  Screen Info's Ports required on a custom data path used to read the
  highest port DRAWN, so 20 ports of 8 drawn on a 450-cabinet wall read 20.
  It now reads the fewest ports any automatic flow pattern needs in the
  screen's Organized or Max Capacity setting. The drawn ports are still the
  ones the cards, the port labels and the canvas count
  (getLayerPortsRequired).

* "in this example file i can go 8 panels wide per port. so i should be able
  to do 8 panels and then start a new port but it errors out". Organized
  packs whole rows (or columns); a row longer than one port used to be a
  capacity error and 0 ports. It is now cut into ports of whole cabinets
  along the row, read from the pattern's start side (the way the custom
  Apply Pattern fill has always cut a long line), and no port carries on
  onto the next row. A row that fits maps exactly as before.

Run locally:
    python -m pytest tests/test_custom_ports_minimum.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

import scr_project  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


# A hand-built project swapped in for one evaluate and put back in a
# finally, so nothing reaches the server or leaks into the next test.
HELPERS_JS = r"""
window.__cpm = {
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'Wide', type: 'screen', visible: true, canvas_id: 'c1',
            columns: 90, rows: 5, cabinet_width: 192, cabinet_height: 384,
            panel_width_mm: 500, panel_height_mm: 1000,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 200, powerVoltage: 208, powerAmperage: 25,
            processorType: 'novastar-armor', bitDepth: 8, frameRate: 60,
            lowLatency: false, rotation: 0,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-h', powerOrganized: true, powerMaximize: false,
            customPortPaths: {}, customPortIndex: 1, customPortOverrides: [],
        }, opts || {});
        const panels = [];
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    id: r * o.columns + c + 1, number: r * o.columns + c + 1,
                    row: r, col: c,
                    x: o.offset_x + c * o.cabinet_width,
                    y: o.offset_y + r * o.cabinet_height,
                    width: o.cabinet_width, height: o.cabinet_height,
                    hidden: false, blank: false, halfTile: 'none',
                    is_color1: (r + c) % 2 === 0,
                });
            }
        }
        o.panels = panels;
        return o;
    },

    // `count` ports of `per` cabinets, drawn along row 0 then row 1, the
    // shape the owner drew (20 ports of 8 = 160 of 450 cabinets).
    drawPorts(layer, count, per) {
        const order = [];
        for (let r = 0; r < layer.rows; r++) {
            for (let c = 0; c < layer.columns; c++) order.push({ row: r, col: c });
        }
        layer.flowPattern = 'custom';
        layer.customPortPaths = {};
        for (let n = 1; n <= count; n++) {
            layer.customPortPaths[n] = order.slice((n - 1) * per, n * per);
        }
        layer.customPortIndex = count;
    },

    withProject(layers, fn) {
        const app = window.app;
        const r = window.canvasRenderer;
        const saved = {
            project: app.project, currentLayer: app.currentLayer,
            selectedLayerIds: app.selectedLayerIds,
            customSelection: app.customSelection,
            history: app.history, historyIndex: app.historyIndex,
            updateLayers: app.updateLayers, renderLayers: app.renderLayers,
            loadLayerToInputs: app.loadLayerToInputs,
            saveClientSideProperties: app.saveClientSideProperties,
            toast: app._toast, viewMode: r.viewMode,
        };
        app.updateLayers = () => {};
        app.renderLayers = () => {};
        app.loadLayerToInputs = () => {};
        app.saveClientSideProperties = () => {};
        app._toast = () => {};
        app.project = {
            layers, groups: [],
            canvases: [{
                id: 'c1', name: 'Canvas 1', workspace_x: 0, workspace_y: 0,
                show_workspace_x: 0, show_workspace_y: 0,
                raster_width: 32768, raster_height: 8192,
                show_raster_width: 32768, show_raster_height: 8192,
                color: '#ff0000', visible: true,
            }],
            active_canvas_id: 'c1',
        };
        app.currentLayer = layers[0] || null;
        app.selectedLayerIds = new Set(layers.map(l => l.id));
        app.customSelection = new Set();
        app.history = []; app.historyIndex = -1;
        r.viewMode = 'data-flow';
        try {
            return fn(app);
        } finally {
            Object.assign(app, {
                project: saved.project, currentLayer: saved.currentLayer,
                selectedLayerIds: saved.selectedLayerIds,
                customSelection: saved.customSelection,
                history: saved.history, historyIndex: saved.historyIndex,
                updateLayers: saved.updateLayers, renderLayers: saved.renderLayers,
                loadLayerToInputs: saved.loadLayerToInputs,
                saveClientSideProperties: saved.saveClientSideProperties,
                _toast: saved.toast,
            });
            r.viewMode = saved.viewMode;
            r.render();
        }
    },

    // The emitted map, port by port: the cells in feed order and the
    // reserved rectangle each port's cabinets make.
    portMap(app, layer) {
        const a = app.calculatePortAssignments(layer) || [];
        const by = new Map();
        a.forEach(x => {
            if (!by.has(x.port)) by.set(x.port, []);
            by.get(x.port).push(x.panel);
        });
        const ports = [...by.keys()].sort((p, q) => p - q).map(p => {
            const ps = by.get(p);
            const minX = Math.min(...ps.map(q => q.x)), minY = Math.min(...ps.map(q => q.y));
            const maxX = Math.max(...ps.map(q => q.x + q.width));
            const maxY = Math.max(...ps.map(q => q.y + q.height));
            return { port: p, cells: ps.map(q => [q.row, q.col]),
                     rect: (maxX - minX) * (maxY - minY) };
        });
        return {
            ports, auto: layer._autoPortsRequired,
            error: layer._capacityError ? layer._capacityError.unitType : null,
            capacity: app.calculatePortCapacity(layer.bitDepth, layer.frameRate,
                                                layer.processorType, !!layer.lowLatency),
        };
    },

    readout(app) {
        app.updatePortCapacityDisplay();
        const el = document.getElementById('ports-required');
        return el ? el.textContent.trim() : null;
    },
};
"""


def _port_map(page, opts):
    return page.evaluate("""(opts) => {
        const h = window.__cpm;
        const s = h.screen(opts);
        return h.withProject([s], app => h.portMap(app, s));
    }""", opts)


# ── Organized splits a row too long for one port ───────────────────────


@pytest.mark.parametrize("pattern,forward", [('tl-h', True), ('tr-h', False),
                                             ('bl-h', True), ('br-h', False)])
def test_organized_splits_a_long_row_into_ports_of_eight(page, pattern, forward):
    """90 wide at 8 a port: each row is 11 ports of 8 and one of 2, 12 a
    row, 60 for the wall, each read from the pattern's start side, and no
    port carries on onto the next row."""
    got = _port_map(page, {'flowPattern': pattern})
    assert got['error'] is None, got['error']
    assert got['auto'] == 60
    ports = got['ports']
    assert len(ports) == 60
    assert [len(p['cells']) for p in ports] == ([8] * 11 + [2]) * 5
    for p in ports:
        assert p['rect'] <= got['capacity'], p
        assert len({r for r, _ in p['cells']}) == 1, f"port {p['port']} spans rows"
    rows_in_order = [0, 1, 2, 3, 4] if pattern.startswith('t') else [4, 3, 2, 1, 0]
    cols = list(range(90)) if forward else list(range(89, -1, -1))
    for i, row in enumerate(rows_in_order):
        run = [c for p in ports[i * 12:(i + 1) * 12] for c in p['cells']]
        assert run == [[row, c] for c in cols], f"row {row} read out of order"


def test_vertical_first_on_the_same_wall_is_whole_columns(page):
    """A column of 5 fits a port (two do not on Armor's rectangle), so
    vertical-first is still one whole column a port, serpentine restarted
    from the top on every port, 90 ports."""
    got = _port_map(page, {'flowPattern': 'tl-v'})
    assert got['error'] is None
    assert got['auto'] == 90
    assert [p['cells'] for p in got['ports']] == [
        [[r, c] for r in range(5)] for c in range(90)]


def test_a_long_column_splits_the_same_way(page):
    """Vertical-first with columns longer than a port: 5 wide x 90 tall of
    384 x 192 cabinets. 659,722 px over 384 x 192 = 8 a port, so each
    column is 11 ports of 8 and one of 2. Numbered Down (column by
    column), port 1..12 are column 0 from the top."""
    got = _port_map(page, {'columns': 5, 'rows': 90, 'cabinet_width': 384,
                           'cabinet_height': 192, 'flowPattern': 'tl-v',
                           'portNumberOrder': 'down'})
    assert got['error'] is None
    assert [len(p['cells']) for p in got['ports']] == ([8] * 11 + [2]) * 5
    first = [c for p in got['ports'][:12] for c in p['cells']]
    assert first == [[r, 0] for r in range(90)]


def test_rows_that_fit_map_exactly_as_before(page):
    """A wall whose rows fit is untouched: Brompton at 32 cabinets of
    128 x 128 a port, 10 wide x 8 tall. Three whole rows a port, each port
    snaking from the left: rows 0-2, 3-5, 6-7."""
    got = _port_map(page, {'columns': 10, 'rows': 8, 'cabinet_width': 128,
                           'cabinet_height': 128, 'processorType': 'brompton'})
    assert got['error'] is None

    def snake(rows):
        out = []
        for i, r in enumerate(rows):
            cols = range(10) if i % 2 == 0 else range(9, -1, -1)
            out.extend([r, c] for c in cols)
        return out
    assert [p['cells'] for p in got['ports']] == [
        snake([0, 1, 2]), snake([3, 4, 5]), snake([6, 7])]


def test_one_cabinet_bigger_than_a_port_is_still_an_error(page):
    got = _port_map(page, {'columns': 4, 'rows': 2, 'cabinet_width': 1200,
                           'cabinet_height': 1200})
    assert got['error'] == 'panel'
    assert got['ports'] == []


def test_hidden_cabinets_in_a_split_row_take_no_port(page):
    """Hidden cabinets are skipped and a hole inside a port's span is paid
    for by its rectangle, never added on top."""
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen({ rows: 1 });
        s.panels.filter(p => p.col >= 3 && p.col <= 5).forEach(p => { p.hidden = true; });
        return h.withProject([s], app => h.portMap(app, s));
    }""")
    assert got['error'] is None
    for p in got['ports']:
        assert p['rect'] <= got['capacity']
        assert not any(3 <= c <= 5 for _, c in p['cells'])
    assert sum(len(p['cells']) for p in got['ports']) == 87


def test_the_scr_export_walk_splits_the_same_way(page):
    """The .scr export walks the wall in Python (scr_project), and it must
    agree with the app port for port."""
    js = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen({});
        return h.withProject([s], app => ({
            screen: JSON.parse(JSON.stringify(s)),
            map: h.portMap(app, s),
        }));
    }""")
    items = scr_project.calculate_port_assignments(js['screen'])
    by = {}
    for it in items:
        by.setdefault(it['port'], []).append([it['panel']['row'], it['panel']['col']])
    py = [by[k] for k in sorted(by)]
    assert py == [p['cells'] for p in js['map']['ports']]


# ── Ports required reads the fewest ports, not the ports drawn ─────────


def _readouts(page, opts, count, per):
    return page.evaluate("""([opts, count, per]) => {
        const h = window.__cpm;
        const out = {};
        ['organized', 'max-capacity'].forEach(mode => {
            const s = h.screen(Object.assign({}, opts, { portMappingMode: mode }));
            h.drawPorts(s, count, per);
            out[mode] = h.withProject([s], app => {
                const shown = h.readout(app);
                // The same wall on each automatic pattern, for the minimum.
                const perPattern = {};
                ['tl-h', 'tl-v', 'tr-h', 'tr-v', 'bl-h', 'bl-v', 'br-h', 'br-v'].forEach(p => {
                    const a = h.screen(Object.assign({}, opts,
                        { portMappingMode: mode, flowPattern: p }));
                    app.calculatePortAssignments(a);
                    perPattern[p] = a._capacityError ? null : a._autoPortsRequired;
                });
                return {
                    shown,
                    minimum: app.getLayerPortsMinimum(s),
                    drawn: app.getLayerPortsRequired(s),
                    portsRequiredField: s._portsRequired,
                    stillCustom: s.flowPattern,
                    perPattern,
                };
            });
        });
        return out;
    }""", [opts, count, per])


def test_owner_wall_with_twenty_ports_drawn_reads_the_minimum(page):
    """The owner's wall: 20 ports of 8 drawn over 160 of 450 cabinets."""
    got = _readouts(page, {}, 20, 8)
    for mode, r in got.items():
        fewest = min(v for v in r['perPattern'].values() if v)
        assert r['minimum'] == fewest, (mode, r)
        assert r['shown'] == str(fewest), (mode, r)
        assert r['shown'] != '20', mode
        # The drawn ports are still what the cards and labels count.
        assert r['drawn'] == 20 and r['portsRequiredField'] == 20, (mode, r)
        assert r['stillCustom'] == 'custom'
    assert got['organized']['minimum'] == 60
    assert got['max-capacity']['minimum'] <= got['organized']['minimum']


def test_a_fully_drawn_custom_wall_reads_the_minimum_too(page):
    """Every cabinet drawn, one whole column of 5 a port: 90 ports drawn.
    Ports required is still the fewest the wall needs, not 90."""
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const out = {};
        ['organized', 'max-capacity'].forEach(mode => {
            const s = h.screen({ portMappingMode: mode });
            s.flowPattern = 'custom';
            s.customPortPaths = {};
            for (let c = 0; c < 90; c++) {
                s.customPortPaths[c + 1] = [0, 1, 2, 3, 4].map(r => ({ row: r, col: c }));
            }
            s.customPortIndex = 90;
            out[mode] = h.withProject([s], app => {
                const best = app.getAutoPortsMinimum(s);
                return { shown: h.readout(app), drawn: app.getLayerPortsRequired(s),
                         best: best.ports };
            });
        });
        return out;
    }""")
    assert got['organized']['drawn'] == 90
    assert got['organized']['shown'] == '60'
    assert got['max-capacity']['drawn'] == 90
    assert got['max-capacity']['shown'] == str(got['max-capacity']['best'])
    assert got['max-capacity']['best'] < 90


def test_an_automatic_screen_reads_its_own_walk(page):
    """Automatic screens are unchanged: the readout is the walk the screen
    is on (tl-v Organized here, 90), not the minimum across patterns."""
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen({ flowPattern: 'tl-v' });
        return h.withProject([s], app => ({ shown: h.readout(app),
                                            minimum: app.getLayerPortsMinimum(s) }));
    }""")
    assert got == {'shown': '90', 'minimum': 90}


def test_the_minimum_leaves_the_screens_own_walk_alone(page):
    """Working the minimum out walks the screen eight times; afterwards its
    own bookkeeping is what its own walk wrote, and its pattern is still
    custom."""
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen({});
        h.drawPorts(s, 3, 8);
        return h.withProject([s], app => {
            app.calculatePortAssignments(s);
            const before = { auto: s._autoPortsRequired, err: s._capacityError };
            const best = app.getAutoPortsMinimum(s);
            return { before, after: { auto: s._autoPortsRequired, err: s._capacityError },
                     pattern: s.flowPattern, best: best.ports };
        });
    }""")
    assert got['before'] == got['after']
    assert got['pattern'] == 'custom'
    assert got['best'] == 60


def test_custom_apply_pattern_organized_splits_the_same_way(page):
    """The custom Apply Pattern fill in Organized cuts the owner's 90-wide
    rows the way the automatic walk now does: 60 ports, 8 x 11 and 2 a row,
    every row from the left."""
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen({});
        s.flowPattern = 'custom';
        const auto = h.screen({});
        return h.withProject([s], app => {
            app.selectPanelsInRect(s, { x1: 1, y1: 1, x2: 90 * 192 - 1, y2: 5 * 384 - 1 });
            const selected = app.customSelection.size;
            app.applyPatternToSelection('tl-h');
            const paths = s.customPortPaths || {};
            const nums = Object.keys(paths).map(Number).sort((a, b) => a - b);
            const drawn = nums.map(n => paths[n].map(e => [e.row, e.col]));
            const walked = h.portMap(app, auto).ports.map(p => p.cells);
            return { selected, drawn, walked };
        });
    }""")
    assert got['selected'] == 450
    assert [len(p) for p in got['drawn']] == ([8] * 11 + [2]) * 5
    assert got['drawn'] == got['walked']


# ── The Port numbers switch (portNumberOrder: 'across' | 'down') ──────
#
# The owner's ruling, 2026-11-01: the ports Organized cuts from a long row
# stay the same runs; Down numbers them down the stacks (port 1 row 1
# cabinets 1-8, port 2 row 2 cabinets 1-8, ... port 6 back at row 1,
# cabinets 9-16). Across, and a show without the field, is the numbering
# the split gives on its own.


def _cells(ports):
    return [p['cells'] for p in ports]


def _run(row, cols):
    return [[row, c] for c in cols]


def test_down_numbers_the_owner_wall_down_the_stacks(page):
    got = _port_map(page, {'portNumberOrder': 'down'})
    assert got['error'] is None and got['auto'] == 60
    cells = _cells(got['ports'])
    for r in range(5):
        assert cells[r] == _run(r, range(8)), f"port {r + 1}"
    assert cells[5] == _run(0, range(8, 16))
    assert cells[6] == _run(1, range(8, 16))
    # The last stack is the 2-cabinet remainder of every row.
    assert cells[55:] == [_run(r, [88, 89]) for r in range(5)]
    # The same runs as Across, only numbered differently.
    across = _cells(_port_map(page, {})['ports'])
    assert sorted(map(str, cells)) == sorted(map(str, across))


def test_across_and_a_show_without_the_field_number_along_the_rows(page):
    missing = _cells(_port_map(page, {})['ports'])
    across = _cells(_port_map(page, {'portNumberOrder': 'across'})['ports'])
    assert missing == across
    assert across[0] == _run(0, range(8)) and across[1] == _run(0, range(8, 16))
    assert across[11] == _run(0, [88, 89]) and across[12] == _run(1, range(8))
    got = page.evaluate("""() => window.app.portNumberOrderOf(window.__cpm.screen({}))""")
    assert got == 'across'


def test_down_follows_the_start_corner(page):
    """A bottom-start pattern stacks up from the bottom row, a right-start
    one reads each row and steps its stacks from the right."""
    bl = _cells(_port_map(page, {'flowPattern': 'bl-h', 'portNumberOrder': 'down'})['ports'])
    assert bl[:6] == [_run(4, range(8)), _run(3, range(8)), _run(2, range(8)),
                      _run(1, range(8)), _run(0, range(8)), _run(4, range(8, 16))]
    tr = _cells(_port_map(page, {'flowPattern': 'tr-h', 'portNumberOrder': 'down'})['ports'])
    assert tr[0] == _run(0, range(89, 81, -1))
    assert tr[1] == _run(1, range(89, 81, -1))
    assert tr[5] == _run(0, range(81, 73, -1))


def test_vertical_first_across_numbers_along_the_top_band(page):
    """The mirror image: columns too tall for one port are cut into runs
    down the column, and Across numbers the top run of every column first,
    then goes back to the start for the next band."""
    tall = {'columns': 5, 'rows': 90, 'cabinet_width': 384, 'cabinet_height': 192,
            'flowPattern': 'tl-v'}

    def col(c, rows):
        return [[r, c] for r in rows]
    across = _cells(_port_map(page, dict(tall, portNumberOrder='across'))['ports'])
    assert across[:6] == [col(0, range(8)), col(1, range(8)), col(2, range(8)),
                          col(3, range(8)), col(4, range(8)), col(0, range(8, 16))]
    down = _cells(_port_map(page, dict(tall, portNumberOrder='down'))['ports'])
    assert down[:2] == [col(0, range(8)), col(0, range(8, 16))]
    br = _cells(_port_map(page, dict(tall, flowPattern='br-v', portNumberOrder='across'))['ports'])
    assert br[0] == col(4, range(89, 81, -1))
    assert br[1] == col(3, range(89, 81, -1))


def test_the_switch_does_nothing_where_nothing_splits(page):
    """Max Capacity, and a wall whose rows fit a port, number the same
    either way."""
    for opts in ({'portMappingMode': 'max-capacity'},
                 {'columns': 10, 'rows': 8, 'cabinet_width': 128, 'cabinet_height': 128,
                  'processorType': 'brompton'}):
        a = _cells(_port_map(page, dict(opts, portNumberOrder='across'))['ports'])
        d = _cells(_port_map(page, dict(opts, portNumberOrder='down'))['ports'])
        assert a == d, opts


def test_the_control_shows_only_where_a_row_splits(page):
    got = page.evaluate("""() => {
        const h = window.__cpm, out = {};
        const cases = {
            longRows: {},
            longRowsDown: { portNumberOrder: 'down' },
            maxCapacity: { portMappingMode: 'max-capacity' },
            rowsFit: { columns: 10, rows: 8, cabinet_width: 128, cabinet_height: 128,
                       processorType: 'brompton' },
            customLongRows: { flowPattern: 'custom' },
        };
        Object.keys(cases).forEach(k => {
            const s = h.screen(cases[k]);
            out[k] = h.withProject([s], app => {
                app.updatePortCapacityDisplay();
                const row = document.getElementById('port-number-order-row');
                return {
                    shown: !!row && row.style.display !== 'none',
                    down: document.getElementById('port-number-down').classList.contains('active'),
                    across: document.getElementById('port-number-across').classList.contains('active'),
                };
            });
        });
        return out;
    }""")
    assert got['longRows'] == {'shown': True, 'down': False, 'across': True}
    assert got['longRowsDown'] == {'shown': True, 'down': True, 'across': False}
    assert got['maxCapacity']['shown'] is False
    assert got['rowsFit']['shown'] is False
    assert got['customLongRows']['shown'] is True


def test_clicking_down_saves_on_the_screen(page):
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen({});
        return h.withProject([s], app => {
            app.updatePortCapacityDisplay();
            document.getElementById('port-number-down').click();
            const after = s.portNumberOrder;
            document.getElementById('port-number-across').click();
            return { after, back: s.portNumberOrder };
        });
    }""")
    assert got == {'after': 'down', 'back': 'across'}


def test_the_layer_route_keeps_the_field(page):
    """A per-screen PUT keeps portNumberOrder, or the switch would be lost
    on the next save."""
    got = page.evaluate("""async () => {
        const proj = await (await fetch('/api/project')).json();
        const add = await (await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name: 'NUMBERS', columns: 4, rows: 2,
                                   cabinet_width: 128, cabinet_height: 128 }),
        })).json();
        add.portNumberOrder = 'down';
        await fetch('/api/layer/' + add.id, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(add),
        });
        const back = await (await fetch('/api/project')).json();
        const l = back.layers.find(x => x.id === add.id);
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(proj),
        });
        return l ? l.portNumberOrder : null;
    }""")
    assert got == 'down'


def test_custom_apply_pattern_follows_the_switch(page):
    """Apply Pattern in Organized numbers its cut runs the same way the
    automatic walk does: Down gives the walk's Down map."""
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen({ portNumberOrder: 'down' });
        s.flowPattern = 'custom';
        const auto = h.screen({ portNumberOrder: 'down' });
        return h.withProject([s], app => {
            app.selectPanelsInRect(s, { x1: 1, y1: 1, x2: 90 * 192 - 1, y2: 5 * 384 - 1 });
            app.applyPatternToSelection('tl-h');
            const paths = s.customPortPaths || {};
            const nums = Object.keys(paths).map(Number).sort((a, b) => a - b);
            return {
                nums,
                drawn: nums.map(n => paths[n].map(e => [e.row, e.col])),
                walked: h.portMap(app, auto).ports.map(p => p.cells),
                active: s.customPortIndex,
            };
        });
    }""")
    assert got['nums'] == list(range(1, 61))
    assert got['drawn'] == got['walked']
    assert got['drawn'][1] == [[1, c] for c in range(8)]
    assert got['active'] == 60


def test_the_scr_export_numbers_down_too(page):
    js = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen({ portNumberOrder: 'down', flowPattern: 'bl-h' });
        return h.withProject([s], app => ({
            screen: JSON.parse(JSON.stringify(s)),
            map: h.portMap(app, s),
        }));
    }""")
    items = scr_project.calculate_port_assignments(js['screen'])
    by = {}
    for it in items:
        by.setdefault(it['port'], []).append([it['panel']['row'], it['panel']['col']])
    assert [by[k] for k in sorted(by)] == [p['cells'] for p in js['map']['ports']]


def test_labels_and_runs_follow_the_new_numbers(page):
    """Everything downstream reads the walk's port numbers: the run a port
    number names (what the tray, the binder and the processor read) is the
    Down map's, and port 2's label sits on row 2's first cabinet."""
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen({ portNumberOrder: 'down' });
        return h.withProject([s], app => {
            const run = n => (typeof app._dockRunPanels === 'function'
                ? app._dockRunPanels(s, n) : []).map(p => [p.row, p.col]);
            const a = app.calculatePortAssignments(s);
            const start2 = a.find(x => x.port === 2 && x.isPortStart);
            return { run2: run(2), run6: run(6), start2: [start2.panel.row, start2.panel.col],
                     label2: app.getPortLabelText ? app.getPortLabelText(s, 2, 'primary') : null };
        });
    }""")
    assert got['run2'] == [[1, c] for c in range(8)]
    assert got['run6'] == [[0, c] for c in range(8, 16)]
    assert got['start2'] == [1, 0]
