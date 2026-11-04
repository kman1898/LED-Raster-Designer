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
  Apply Pattern fill has always cut a long line), and no port snakes on
  from mid-row onto the next row. A row that fits maps exactly as before.

* 2026-11-04, the same walls: Organized fills its ports "as much as
  possible per the math". The leftovers at the end of consecutive cut
  rows, in the same columns, stack into one port while it carries them:
  the 2-wide leftovers of rows 0-3 are one port of 8 and row 4's is its
  own, so the 90 x 5 wall is 57 ports, no longer 60
  (test_organized_leftover_stacking.py pins the rule itself).

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
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}"
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
        // `halfRow` / `halfCol`: one row of half-height (or one column of
        // half-width) cabinets, the rows below (columns right) moved up.
        const halfRow = o.halfRow, halfCol = o.halfCol;
        delete o.halfRow;
        delete o.halfCol;
        const h = r => (r === halfRow ? o.cabinet_height / 2 : o.cabinet_height);
        const w = c => (c === halfCol ? o.cabinet_width / 2 : o.cabinet_width);
        const panels = [];
        let y = o.offset_y;
        for (let r = 0; r < o.rows; r++) {
            let x = o.offset_x;
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    id: r * o.columns + c + 1, number: r * o.columns + c + 1,
                    row: r, col: c, x, y,
                    width: w(c), height: h(r),
                    hidden: false, blank: false,
                    halfTile: r === halfRow ? 'height' : (c === halfCol ? 'width' : 'none'),
                    is_color1: (r + c) % 2 === 0,
                });
                x += w(c);
            }
            y += h(r);
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


def _wide_cut(rows_in_order, cols, snake=True):
    """The 90-wide wall's ports in walk order (Across): each line's eleven
    runs of 8 from the start side, the leftovers of the first four lines
    stacked into one port after the first line's runs (each line after
    the first running back on a snake), the last line's leftover alone."""
    runs = {r: [[[r, c] for c in cols[i:i + 8]] for i in range(0, 88, 8)] for r in rows_in_order}
    stack = []
    for i, r in enumerate(rows_in_order[:4]):
        left = cols[88:]
        stack.extend([r, c] for c in (left if (i % 2 == 0 or not snake) else left[::-1]))
    out = runs[rows_in_order[0]] + [stack]
    for r in rows_in_order[1:]:
        out += runs[r]
    out.append([[rows_in_order[-1], c] for c in cols[88:]])
    return out


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
    """90 wide at 8 a port: each row is 11 ports of 8 read from the
    pattern's start side, and the 2-wide leftovers of the first four rows
    (in walk order) stack into one port of 8, the last row's alone: 57
    ports. Only the stacked port spans rows."""
    got = _port_map(page, {'flowPattern': pattern})
    assert got['error'] is None, got['error']
    assert got['auto'] == 57
    ports = got['ports']
    assert len(ports) == 57
    for p in ports:
        assert p['rect'] <= got['capacity'], p
    rows_in_order = [0, 1, 2, 3, 4] if pattern.startswith('t') else [4, 3, 2, 1, 0]
    cols = list(range(90)) if forward else list(range(89, -1, -1))
    assert [p['cells'] for p in ports] == _wide_cut(rows_in_order, cols)
    spanning = [p for p in ports if len({r for r, _ in p['cells']}) > 1]
    assert [len(p['cells']) for p in spanning] == [8]


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
    column is 11 ports of 8 and a leftover of 2; columns 0-3's leftovers
    stack across the columns into one port. Numbered Down (column by
    column), ports 1..11 are column 0 from the top and port 12 the
    stacked leftovers."""
    got = _port_map(page, {'columns': 5, 'rows': 90, 'cabinet_width': 384,
                           'cabinet_height': 192, 'flowPattern': 'tl-v',
                           'portNumberOrder': 'down'})
    assert got['error'] is None
    assert [len(p['cells']) for p in got['ports']] == [8] * 56 + [2]
    first = [c for p in got['ports'][:11] for c in p['cells']]
    assert first == [[r, 0] for r in range(88)]
    assert got['ports'][11]['cells'] == [[88, 0], [89, 0], [89, 1], [88, 1],
                                          [88, 2], [89, 2], [89, 3], [88, 3]]


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
                ['tl-h', 'tr-h', 'bl-h', 'br-h', 'tl-v', 'tr-v', 'bl-v', 'br-v'].flatMap(p => [p, p + '-z']).forEach(p => {
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
    assert got['organized']['minimum'] == 57
    assert got['max-capacity']['minimum'] == 58


def test_the_owner_shape_per_pattern_figures(page):
    """What every automatic walk gives on the 90 x 5 Armor wall of full
    192 x 384 cabinets, recorded as found. 8 cabinets a port (9 would
    reserve 663,552 px), so 450 / 8 rounds up to 57 at best. Organized cuts
    each row 8 x 11 + 2 and stacks four rows' leftovers into one port,
    which reaches the 57 on the snake and the Z alike; vertical-first is a
    whole column of 5 a port. Max Capacity on a snake lets a row's last 2
    carry on round the turn, which the Z cannot, so the snake packs
    tighter there."""
    got = page.evaluate("""() => {
        const h = window.__cpm, out = {};
        ['organized', 'max-capacity'].forEach(mode => {
            ['tl-h', 'tl-h-z', 'tl-v', 'tl-v-z'].forEach(p => {
                const s = h.screen({ flowPattern: p, portMappingMode: mode });
                h.withProject([s], app => app.calculatePortAssignments(s));
                out[mode + ' ' + p] = s._capacityError ? 'ERROR' : s._autoPortsRequired;
            });
        });
        return out;
    }""")
    assert got == {
        'organized tl-h': 57, 'organized tl-h-z': 57,
        'organized tl-v': 90, 'organized tl-v-z': 90,
        'max-capacity tl-h': 58, 'max-capacity tl-h-z': 60,
        'max-capacity tl-v': 90, 'max-capacity tl-v-z': 90,
    }, got


def test_a_half_height_last_row_cuts_at_its_own_size(page):
    """The same wall with its last row half tiles (192 x 192), the shape of
    the owner's show: 17 half tiles fit a port, so that row is 17 x 5 + 5,
    6 ports. The full rows are 4 x 11 and their four leftovers one stacked
    port (the half row's 5 sit in other columns and stay apart), so the
    wall is 44 + 1 + 6 = 51 in Organized. Max Capacity reads 52 on the
    snake."""
    got = page.evaluate("""() => {
        const h = window.__cpm, out = {};
        ['organized', 'max-capacity'].forEach(mode => {
            const s = h.screen({ portMappingMode: mode });
            s.panels.filter(p => p.row === 4).forEach(p => { p.height = 192; p.halfTile = 'height'; });
            out[mode] = h.withProject([s], app => {
                const m = h.portMap(app, s);
                return { auto: m.auto, err: m.error,
                         last: m.ports.filter(p => p.cells[0][0] === 4).map(p => p.cells.length) };
            });
        });
        return out;
    }""")
    assert got['organized'] == {'auto': 51, 'err': None, 'last': [17, 17, 17, 17, 17, 5]}
    assert got['max-capacity']['auto'] == 52 and got['max-capacity']['err'] is None


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
    assert got['organized']['shown'] == '57'
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
    """Working the minimum out walks the screen sixteen times (eight snakes, eight Z); afterwards its
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
    assert got['best'] == 57


def test_custom_apply_pattern_organized_splits_the_same_way(page):
    """The custom Apply Pattern fill in Organized cuts the owner's 90-wide
    rows the way the automatic walk now does: 57 ports, 8 x 11 a row from
    the left, four rows' leftovers stacked into one port and the last
    row's alone."""
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
    assert got['drawn'] == _wide_cut([0, 1, 2, 3, 4], list(range(90)))
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
    assert got['error'] is None and got['auto'] == 57
    cells = _cells(got['ports'])
    for r in range(5):
        assert cells[r] == _run(r, range(8)), f"port {r + 1}"
    assert cells[5] == _run(0, range(8, 16))
    assert cells[6] == _run(1, range(8, 16))
    # The last stack is the 2-cabinet remainder of every row: rows 0-3's
    # stacked into one port, numbered by its first cabinet, then row 4's.
    assert cells[55:] == [_run(0, [88, 89]) + _run(1, [89, 88]) + _run(2, [88, 89])
                          + _run(3, [89, 88]), _run(4, [88, 89])]
    # The same runs as Across, only numbered differently.
    across = _cells(_port_map(page, {})['ports'])
    assert sorted(map(str, cells)) == sorted(map(str, across))


def test_across_and_a_show_without_the_field_number_along_the_rows(page):
    missing = _cells(_port_map(page, {})['ports'])
    across = _cells(_port_map(page, {'portNumberOrder': 'across'})['ports'])
    assert missing == across
    assert across[0] == _run(0, range(8)) and across[1] == _run(0, range(8, 16))
    # the stacked leftover comes where its first cabinet does, end of row 0
    assert across[11][:2] == _run(0, [88, 89]) and len(across[11]) == 8
    assert across[12] == _run(1, range(8))
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


def test_a_vertical_screen_never_switched_numbers_down_its_columns(page):
    """No portNumberOrder on a vertical-first screen is the walk's own
    order, down each column, and the switch reads Down: an older show keeps
    the numbers it had, and the label says what the map does."""
    tall = {'columns': 5, 'rows': 90, 'cabinet_width': 384, 'cabinet_height': 192,
            'flowPattern': 'tl-v'}
    missing = _cells(_port_map(page, tall)['ports'])
    down = _cells(_port_map(page, dict(tall, portNumberOrder='down'))['ports'])
    assert missing == down
    got = page.evaluate("""(tall) => {
        const h = window.__cpm;
        const s = h.screen(tall);
        return h.withProject([s], app => {
            app.updatePortCapacityDisplay();
            return {
                order: app.portNumberOrderOf(s),
                shown: document.getElementById('port-number-order-row').style.display !== 'none',
                down: document.getElementById('port-number-down').classList.contains('active'),
                field: s.portNumberOrder === undefined,
            };
        });
    }""", tall)
    assert got == {'order': 'down', 'shown': True, 'down': True, 'field': True}


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
    assert got['nums'] == list(range(1, 58))
    assert got['drawn'] == got['walked']
    assert got['drawn'][1] == [[1, c] for c in range(8)]
    assert got['active'] == 57


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


# ── A line cut differently from the stacks ──────────────────────────────
#
# The owner's ruling, 2026-11-02, on an 85 x 5 Armor wall whose bottom row
# is half-height cabinets: rows of 8 a port above, the half row 17 a port
# (17 x 192 x 192 fits 659,722 px, 9 full cabinets do not). "the first
# column should be 1 through 5. then the next column should start at 6-9
# then 10-13 with 14 being next under 13 and one over to the right". Each
# stack numbers its own rows; a run of the line cut another way joins the
# stack its first cabinet sits under, in line order.

HALF_BOTTOM = {'columns': 85, 'rows': 5, 'halfRow': 4, 'portNumberOrder': 'down'}
HALF_RIGHT = {'columns': 5, 'rows': 85, 'cabinet_width': 384, 'cabinet_height': 192,
              'halfCol': 4, 'flowPattern': 'tl-v', 'portNumberOrder': 'across'}


def _stacks_with_half(full_runs, half_runs, stack_starts, half_starts, before):
    """The expected order: stack k is the full lines' k-th runs in line
    order; each half-line run goes into the stack its first cabinet sits
    under, ahead of the stack's own runs when its line comes first."""
    out = []
    for k, start in enumerate(stack_starts):
        end = stack_starts[k + 1] if k + 1 < len(stack_starts) else None
        mine = [h for h, at in zip(half_runs, half_starts)
                if at >= start and (end is None or at < end)]
        out.extend((mine if before else []) + full_runs[k] + ([] if before else mine))
    return out


def _owner_down(pattern='tl-h'):
    """Expected Down numbering of HALF_BOTTOM read from `pattern`."""
    forward = 'l-' in pattern
    top_start = pattern.startswith('t')
    full_rows = [0, 1, 2, 3] if top_start else [3, 2, 1, 0]
    cols = list(range(85)) if forward else list(range(84, -1, -1))
    full_runs = [[_run(r, cols[i:i + 8]) for r in full_rows] for i in range(0, 85, 8)]
    half_runs = [_run(4, cols[i:i + 17]) for i in range(0, 85, 17)]
    return _stacks_with_half(full_runs, half_runs, list(range(0, 85, 8)),
                             list(range(0, 85, 17)), before=not top_start)


def test_down_puts_a_half_row_run_under_the_stack_it_starts_in(page):
    got = _port_map(page, HALF_BOTTOM)
    assert got['error'] is None and got['auto'] == 49
    cells = _cells(got['ports'])
    # The owner's words: 1-5 the first stack and the half row's first run,
    # 6-9 the next stack, 10-13, then 14 under 13 one over to the right.
    assert cells[:5] == [_run(r, range(8)) for r in range(4)] + [_run(4, range(17))]
    assert cells[5:9] == [_run(r, range(8, 16)) for r in range(4)]
    assert cells[9:13] == [_run(r, range(16, 24)) for r in range(4)]
    assert cells[13] == _run(4, range(17, 34))
    assert cells == _owner_down()
    across = _cells(_port_map(page, dict(HALF_BOTTOM, portNumberOrder='across'))['ports'])
    assert sorted(map(str, cells)) == sorted(map(str, across))


@pytest.mark.parametrize("pattern", ['tr-h', 'bl-h', 'br-h'])
def test_a_half_row_follows_the_start_corner(page, pattern):
    """The same rule from every corner: a right start counts the stacks
    from the right, and a bottom start numbers the half row (its first
    line) first in each stack it starts under."""
    got = _cells(_port_map(page, dict(HALF_BOTTOM, flowPattern=pattern))['ports'])
    assert got == _owner_down(pattern)


def test_a_differently_cut_top_row_comes_first_in_its_stack(page):
    got = _cells(_port_map(page, dict(HALF_BOTTOM, halfRow=0))['ports'])
    assert got[:5] == [_run(0, range(17))] + [_run(r, range(8)) for r in range(1, 5)]
    assert got[5:9] == [_run(r, range(8, 16)) for r in range(1, 5)]
    assert got[9] == _run(0, range(17, 34))
    assert got[10:14] == [_run(r, range(16, 24)) for r in range(1, 5)]
    assert len(got) == 49


def test_vertical_across_puts_a_half_column_run_in_its_band(page):
    """The vertical mirror: columns cut 8 tall, a half-width last column
    17 tall; Across numbers each band of the full columns, and a half
    column run joins the band its first cabinet sits in."""
    def col(c, rows):
        return [[r, c] for r in rows]
    got = _cells(_port_map(page, HALF_RIGHT)['ports'])
    assert got[:5] == [col(c, range(8)) for c in range(4)] + [col(4, range(17))]
    assert got[5:9] == [col(c, range(8, 16)) for c in range(4)]
    assert got[9:13] == [col(c, range(16, 24)) for c in range(4)]
    assert got[13] == col(4, range(17, 34))
    assert len(got) == 49


def test_across_with_a_half_row_still_numbers_along_the_rows(page):
    got = _cells(_port_map(page, dict(HALF_BOTTOM, portNumberOrder='across'))['ports'])
    want = [_run(r, range(c, min(c + 8, 85))) for r in range(4) for c in range(0, 85, 8)]
    want += [_run(4, range(c, c + 17)) for c in range(0, 85, 17)]
    assert got == want


def test_custom_apply_pattern_numbers_a_half_row_the_same_way(page):
    got = page.evaluate("""(opts) => {
        const h = window.__cpm;
        const s = h.screen(opts);
        s.flowPattern = 'custom';
        const auto = h.screen(opts);
        return h.withProject([s], app => {
            app.selectPanelsInRect(s, { x1: 1, y1: 1, x2: 85 * 192 - 1, y2: 4 * 384 + 191 });
            app.applyPatternToSelection('tl-h');
            const paths = s.customPortPaths || {};
            const nums = Object.keys(paths).map(Number).sort((a, b) => a - b);
            return {
                drawn: nums.map(n => paths[n].map(e => [e.row, e.col])),
                walked: h.portMap(app, auto).ports.map(p => p.cells),
            };
        });
    }""", HALF_BOTTOM)
    assert got['walked'] == _owner_down()
    assert got['drawn'] == got['walked']


@pytest.mark.parametrize("opts", [
    HALF_BOTTOM,
    dict(HALF_BOTTOM, flowPattern='tr-h'),
    dict(HALF_BOTTOM, flowPattern='bl-h'),
    dict(HALF_BOTTOM, flowPattern='br-h'),
    dict(HALF_BOTTOM, halfRow=0),
    dict(HALF_BOTTOM, portNumberOrder='across'),
    HALF_RIGHT,
    dict(HALF_RIGHT, flowPattern='br-v'),
    {'portNumberOrder': 'down'},
    dict(HALF_BOTTOM, flowPattern='tr-h', portNumberOrder='across'),
    dict(HALF_BOTTOM, flowPattern='br-h', portNumberOrder='across'),
    dict(HALF_RIGHT, flowPattern='tr-v'),
    dict(HALF_RIGHT, flowPattern='bl-v', portNumberOrder='down'),
    dict(HALF_RIGHT, flowPattern='br-v-z', portNumberOrder='down'),
], ids=['tl', 'tr', 'bl', 'br', 'top', 'across', 'v-tl', 'v-br', 'uniform',
        'across-tr', 'across-br', 'v-tr', 'v-bl-down', 'v-br-z-down'])
def test_the_scr_export_numbers_a_half_line_the_same_way(page, opts):
    """scr_project.py split_unit and stack_split_runs number every case
    exactly as the app does."""
    js = page.evaluate("""(opts) => {
        const h = window.__cpm;
        const s = h.screen(opts);
        return h.withProject([s], app => ({
            screen: JSON.parse(JSON.stringify(s)),
            map: h.portMap(app, s),
        }));
    }""", opts)
    items = scr_project.calculate_port_assignments(js['screen'])
    by = {}
    for it in items:
        by.setdefault(it['port'], []).append([it['panel']['row'], it['panel']['col']])
    assert [by[k] for k in sorted(by)] == [p['cells'] for p in js['map']['ports']]


def test_split_run_stacks_is_the_old_order_where_every_line_cuts_the_same():
    """Lines cut alike number exactly as before the ruling, with or without
    run positions; a line cut another way goes by its first cabinet."""
    same = [{'line': ln, 'seg': k, 'pos': 8 * k} for ln in range(4) for k in range(11)]
    assert scr_project.split_run_stacks(same) == [i['seg'] for i in same]
    assert scr_project.split_run_stacks([]) == []
    bare = [{'line': ln, 'seg': k} for ln in range(3) for k in range(2)]
    assert scr_project.split_run_stacks(bare) == [0, 1, 0, 1, 0, 1]
    runs = [{'split': i, 'n': n} for n, i in enumerate(same)]
    old = sorted(runs, key=lambda r: (r['split']['seg'], r['split']['line']))
    assert scr_project.stack_split_runs(runs) == old
    odd = same + [{'line': 4, 'seg': k, 'pos': 17 * k} for k in range(5)]
    assert scr_project.split_run_stacks(odd)[-5:] == [0, 2, 4, 6, 8]
    # Lines that lost cabinets at an end to a taken-over port, or start
    # further in, are cut alike and keep numbering by place.
    short = [{'line': ln, 'seg': k, 'pos': 8 * k} for ln in range(5)
             for k in range(12 if ln in (1, 4) else 11)]
    assert scr_project.split_run_stacks(short) == [i['seg'] for i in short]
    shifted = [{'line': ln, 'seg': k, 'pos': 8 * k + (2 if ln % 2 else 0)}
               for ln in range(5) for k in range(11)]
    assert scr_project.split_run_stacks(shifted) == [i['seg'] for i in shifted]


# ── Numbers start where the wall is cabled ──────────────────────────────
#
# The owner, 2026-11-02: "power should be able to start from top right and
# go to the left or bottom right and go to the left, depending on how it
# is cabled. Same with data." The flow pattern's corner is where the
# cabling starts: Across and Down both number from that corner and walk
# away from it, with or without a line cut differently from the rest.

def _expect_from_corner(pattern, lines, length, by_stack):
    """Worked out here on its own. `lines` in walk order, each (line,
    cabinets a port); every line is cut from the pattern's start side, and
    a port's stack is the stack of the most finely cut lines its first
    cabinet sits in. By stacks: stack, then walk order; else walk order."""
    vertical = '-v' in pattern
    forward = pattern.startswith('t') if vertical else 'l-' in pattern
    along = list(range(length)) if forward else list(range(length - 1, -1, -1))
    stack_len = min(per for _, per in lines)
    keyed = []
    for walk_at, (line, per) in enumerate(lines):
        for seg, start in enumerate(range(0, length, per)):
            span = along[start:start + per]
            cells = [[r, line] for r in span] if vertical else _run(line, span)
            keyed.append(((start // stack_len) if by_stack else walk_at, walk_at, seg, cells))
    keyed.sort(key=lambda k: k[:3])
    return [k[3] for k in keyed]


@pytest.mark.parametrize("pattern", ['tl-h', 'tr-h', 'bl-h', 'br-h', 'tr-h-z', 'br-h-z'])
@pytest.mark.parametrize("half", [None, 4], ids=['full', 'half'])
def test_across_numbers_from_the_start_corner(page, pattern, half):
    rows = [0, 1, 2, 3, 4] if pattern.startswith('t') else [4, 3, 2, 1, 0]
    opts = dict(HALF_BOTTOM, flowPattern=pattern, portNumberOrder='across', halfRow=half)
    got = _cells(_port_map(page, opts)['ports'])
    lines = [(r, 17 if r == half else 8) for r in rows]
    assert got == _expect_from_corner(pattern, lines, 85, by_stack=False)
    assert got[0][0] == [rows[0], 0 if 'l-' in pattern else 84]


@pytest.mark.parametrize("pattern", ['tl-v', 'tr-v', 'bl-v', 'br-v', 'tr-v-z', 'br-v-z'])
@pytest.mark.parametrize("order", ['across', 'down'])
def test_a_half_column_numbers_from_the_start_corner(page, pattern, order):
    """Vertical first: Across numbers the bands of runs across the
    columns, Down down each column; a right start steps the columns right
    to left and a bottom start reads each column from the bottom."""
    cols = [0, 1, 2, 3, 4] if 'l-' in pattern else [4, 3, 2, 1, 0]
    got = _cells(_port_map(page, dict(HALF_RIGHT, flowPattern=pattern,
                                      portNumberOrder=order))['ports'])
    lines = [(c, 17 if c == 4 else 8) for c in cols]
    assert got == _expect_from_corner(pattern, lines, 85, by_stack=order == 'across')
    assert got[0][0] == [0 if pattern.startswith('t') else 84, cols[0]]


# ── Grouped screens that overlap in Pixel Map (QA, 1.6.0) ────────────────
#
# A duplicate keeps its Pixel Map offset, so a screen duplicated and grouped
# with its original overlaps it. On a rectangle processor the port's rect
# took the overlap once and one port carried both screens: 48 cabinets of
# 16,384 px (786,432) on a 659,722 px port. A port is never charged less
# than its cabinets' own pixels.

def test_grouped_screens_that_overlap_never_overload_a_port(page):
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const a = h.screen({ id: 1, name: 'A', columns: 8, rows: 3,
                             cabinet_width: 128, cabinet_height: 128, group_id: 'g1' });
        const b = h.screen({ id: 2, name: 'B', columns: 8, rows: 3,
                             cabinet_width: 128, cabinet_height: 128, group_id: 'g1',
                             offset_x: 50, offset_y: 50 });
        return h.withProject([a, b], app => {
            app.project.groups = [{ id: 'g1', name: 'Group 1', layer_ids: [1, 2] }];
            const m = app._dockBuildDataMap();
            const by = new Map();
            [a, b].forEach(l => l.panels.forEach(p => {
                const v = m.get(p);
                if (!v) return;
                const k = v.ownerId + ':' + v.portNum;
                if (!by.has(k)) by.set(k, []);
                by.get(k).push(p);
            }));
            const cap = app.calculatePortCapacity(a.bitDepth, a.frameRate, a.processorType, false);
            return { cap, ports: [...by].map(([k, ps]) => ({ k, n: ps.length,
                own: ps.reduce((s, p) => s + p.width * p.height, 0),
                load: window.canvasRenderer.getPortPixelLoad(a, ps) })) };
        });
    }""")
    assert sum(p['n'] for p in got['ports']) == 48
    assert len(got['ports']) >= 2, got
    for p in got['ports']:
        assert p['own'] <= got['cap'], p
        assert p['load'] >= p['own'], p


def test_overlapping_cabinets_are_charged_their_own_pixels(page):
    got = page.evaluate("""() => {
        const layer = { processorType: 'novastar-armor' };
        const ps = [0, 1].map(i => ({ x: 0, y: 0, width: 128, height: 128 }));
        return window.canvasRenderer.getPortPixelLoad(layer, ps);
    }""")
    assert got == 2 * 128 * 128
