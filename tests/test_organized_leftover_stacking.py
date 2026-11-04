"""Organized stacks the leftovers at the end of its cut rows.

The owner's ruling, 2026-11-04, on an 84 x 5 wall of 192 x 384 cabinets on
NovaStar COEX 1G at 8-bit 60 Hz (659,722 px a port: 8 full cabinets, or 17
of the half-height ones on the bottom row), walked tl-h, Organized,
numbered Down: Organized should fill its ports "as much as possible per
the math". Each full row cuts into ten ports of 8 and a leftover of 4
(columns 80-83). Those leftovers used to be four ports of 4; now the
leftovers of consecutive rows in the same columns stack into one port
while it carries them: rows 0-1 are one port of 8, rows 2-3 another, and
the wall is 47 ports instead of 49.

* A full row still cuts into ports of whole cabinets from the start side,
  and no port snakes on from mid-row. A stacked port is a clean rectangle,
  one cable through it (the second row runs back on a snake).
* A 2-wide leftover stacks four rows, a 3-wide one two.
* A half-height row joins a stack only where its cabinets sit in exactly
  the same columns and the port's own test (the COEX 1G / Armor reserved
  rectangle, or the pixel sum) passes with it.
* Vertical patterns stack column-end leftovers across adjacent columns.
* The automatic walk, the custom Apply Pattern fill and the .scr export's
  Python walk make the same ports and number them the same way, Down and
  Across; a stacked port takes its number from its first cabinet.
* Max Capacity is unchanged, and so is an opened show's custom drawing.

Run locally:
    python -m pytest tests/test_organized_leftover_stacking.py -v --browser chromium
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
    for ep in ('save-file', 'open-file', 'select-directory'):
        pg.route(f'**/api/native-dialog/{ep}', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body='{"cancelled": true, "path": null}'))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.evaluate(HELPERS_JS)
    yield pg
    context.close()


# A hand-built screen swapped in for one evaluate and put back in a
# finally, so nothing reaches the server or leaks into the next test.
HELPERS_JS = r"""
window.__ols = {
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'Stack', type: 'screen', visible: true, canvas_id: 'c1',
            columns: 84, rows: 5, cabinet_width: 192, cabinet_height: 384,
            panel_width_mm: 500, panel_height_mm: 1000,
            offset_x: 0, offset_y: 0, panel_weight: 20, weight_unit: 'kg',
            panelWatts: 200, powerVoltage: 208, powerAmperage: 25,
            processorType: 'novastar-coex-1g', bitDepth: 8, frameRate: 60,
            lowLatency: false, rotation: 0, halfRow: 4,
            flowPattern: 'tl-h', portMappingMode: 'organized', portNumberOrder: 'down',
            powerFlowPattern: 'tl-h', powerOrganized: true, powerMaximize: false,
            customPortPaths: {}, customPortIndex: 1, customPortOverrides: [],
        }, opts || {});
        // `halfRow` / `halfCol`: one row of half-height (or one column of
        // half-width) cabinets; null for none.
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
                    row: r, col: c, x, y, width: w(c), height: h(r),
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

    withProject(layers, fn) {
        const app = window.app;
        const r = window.canvasRenderer;
        const saved = {
            project: app.project, currentLayer: app.currentLayer,
            selectedLayerIds: app.selectedLayerIds, customSelection: app.customSelection,
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
                raster_width: 32768, raster_height: 32768,
                show_raster_width: 32768, show_raster_height: 32768,
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
                selectedLayerIds: saved.selectedLayerIds, customSelection: saved.customSelection,
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

    // The walk's ports in number order: each the cells in feed order.
    walk(app, layer) {
        const a = app.calculatePortAssignments(layer) || [];
        const by = new Map();
        a.forEach(x => {
            if (!by.has(x.port)) by.set(x.port, []);
            by.get(x.port).push([x.panel.row, x.panel.col]);
        });
        const nums = [...by.keys()].sort((p, q) => p - q);
        return { nums, ports: nums.map(n => by.get(n)), auto: layer._autoPortsRequired,
                 error: layer._capacityError ? layer._capacityError.unitType : null };
    },

    // Custom mode, every cabinet selected, the pattern tile's fill.
    apply(app, layer, pattern) {
        layer.lastFlowPattern = layer.flowPattern;
        layer.flowPattern = 'custom';
        layer.panels.forEach(p => app.customSelection.add(app.getScopedPanelKey(layer.id, p)));
        app.applyPatternToSelection(pattern);
        const paths = layer.customPortPaths || {};
        const nums = Object.keys(paths).map(Number).filter(n => (paths[n] || []).length)
            .sort((a, b) => a - b);
        return { nums, ports: nums.map(n => paths[n].map(e => [e.row, e.col])) };
    },

    // Walk, then Apply on a copy, of the same screen.
    both(opts) {
        const h = window.__ols;
        const s = h.screen(opts);
        const c = h.screen(opts);
        const walked = h.withProject([s], app => h.walk(app, s));
        const applied = h.withProject([c], app => h.apply(app, c, s.flowPattern));
        return { walked, applied, screen: JSON.parse(JSON.stringify(s)) };
    },
};
"""


def _both(page, opts=None):
    return page.evaluate("(o) => window.__ols.both(o)", opts or {})


def _python(screen):
    by = {}
    for it in scr_project.calculate_port_assignments(screen):
        by.setdefault(it['port'], []).append([it['panel']['row'], it['panel']['col']])
    return [by[k] for k in sorted(by)]


def _run(row, cols):
    return [[row, c] for c in cols]


def _snake(rows, cols):
    """A stacked leftover read as one cable: the first row from the start
    side, the next back."""
    out = []
    for i, r in enumerate(rows):
        out.extend(_run(r, cols if i % 2 == 0 else list(reversed(cols))))
    return out


EIGHTS = [list(range(c, c + 8)) for c in range(0, 80, 8)]
HALVES = [list(range(c, min(c + 17, 84))) for c in range(0, 84, 17)]
LEFT = [80, 81, 82, 83]


def _owner_down():
    """The test wall numbered Down: each stack of 8-wide runs top to
    bottom, a half-row run under the stack its first cabinet sits under,
    the stacked leftovers last."""
    out = []
    for k, cols in enumerate(EIGHTS):
        out.extend(_run(r, cols) for r in range(4))
        out.extend(_run(4, h) for h in HALVES if cols[0] <= h[0] < cols[0] + 8)
    out.append(_snake([0, 1], LEFT))
    out.append(_snake([2, 3], LEFT))
    return out


def _owner_across():
    """Across: along each row, the stacked leftover numbered where its first
    cabinet (row 0 or row 2, column 80) comes."""
    out = []
    for r in range(4):
        out.extend(_run(r, cols) for cols in EIGHTS)
        if r in (0, 2):
            out.append(_snake([r, r + 1], LEFT))
    out.extend(_run(4, h) for h in HALVES)
    return out


# ── the owner's wall ───────────────────────────────────────────────────


@pytest.mark.parametrize("order,want", [('down', _owner_down), ('across', _owner_across)])
def test_the_owner_wall_stacks_its_leftovers_into_47_ports(page, order, want):
    got = _both(page, {'portNumberOrder': order})
    walked, applied = got['walked'], got['applied']
    assert walked['error'] is None
    assert walked['auto'] == 47
    assert walked['nums'] == list(range(1, 48))
    assert walked['ports'] == want()
    # the custom Apply Pattern fill draws the very same ports, numbers and
    # all, and so does the .scr export's walk
    assert applied['nums'] == list(range(1, 48))
    assert applied['ports'] == walked['ports']
    assert _python(got['screen']) == walked['ports']


def test_the_stacked_ports_are_full_and_the_half_row_is_cut_at_its_own_size(page):
    got = _both(page)['walked']
    sizes = sorted(len(p) for p in got['ports'])
    # 40 runs of 8, the 2 stacked leftovers of 8, the half row 17 x 4 + 16
    assert sizes == [8] * 42 + [16] + [17] * 4
    stacked = [p for p in got['ports'] if len({r for r, _ in p}) > 1]
    assert stacked == [_snake([0, 1], LEFT), _snake([2, 3], LEFT)]


def test_every_readout_agrees_on_47(page):
    """The walk's figure, the Ports required readout, the fewest any
    pattern needs, and on a custom screen with nothing drawn yet the
    automatic figure it falls back on (which used to walk columns: 84)."""
    got = page.evaluate("""() => {
        const h = window.__ols, out = {};
        const s = h.screen({});
        out.auto = h.withProject([s], app => {
            app.updatePortCapacityDisplay();
            return { walk: (app.calculatePortAssignments(s), s._autoPortsRequired),
                     required: app.getLayerPortsRequired(s),
                     minimum: app.getAutoPortsMinimum(s).ports,
                     field: s._portsRequired,
                     shown: document.getElementById('ports-required').textContent.trim() };
        });
        const c = h.screen({});
        c.lastFlowPattern = 'tl-h';
        c.flowPattern = 'custom';
        out.custom = h.withProject([c], app => {
            app.updatePortCapacityDisplay();
            return { walk: (app.calculatePortAssignments(c), c._autoPortsRequired),
                     required: app.getLayerPortsRequired(c),
                     minimum: app.getAutoPortsMinimum(c).ports,
                     field: c._portsRequired,
                     shown: document.getElementById('ports-required').textContent.trim(),
                     pattern: c.flowPattern };
        });
        return out;
    }""")
    assert got['auto'] == {'walk': 47, 'required': 47, 'minimum': 47, 'field': 47, 'shown': '47'}
    assert got['custom'] == {'walk': 47, 'required': 47, 'minimum': 47, 'field': 47,
                             'shown': '47', 'pattern': 'custom'}


def test_max_capacity_is_unchanged(page):
    """Max Capacity packs one continuous snake; nothing about it moved."""
    got = _both(page, {'portMappingMode': 'max-capacity'})['walked']
    assert got['auto'] == 47
    assert got['ports'][0] == _run(0, range(8))
    # the snake carries row 0's last 4 round onto row 1
    assert got['ports'][10] == _run(0, LEFT) + _run(1, [83, 82, 81, 80])


# ── other widths ───────────────────────────────────────────────────────


ARMOR_90 = {'columns': 90, 'processorType': 'novastar-armor', 'halfRow': None}


@pytest.mark.parametrize("pattern", ['tl-h', 'tl-h-z'])
def test_a_two_wide_leftover_stacks_four_rows(page, pattern):
    """90 wide at 8 a port: the 2-wide leftovers of rows 0-3 are one port
    of 8 (the Armor rectangle around them is 384 x 1536), row 4's stays
    on its own. 57 ports, where it was 60. A Z reads every row from the
    start side."""
    got = _both(page, dict(ARMOR_90, flowPattern=pattern, portNumberOrder='down'))
    walked = got['walked']
    assert walked['auto'] == 57
    if pattern == 'tl-h':
        stack = _snake([0, 1, 2, 3], [88, 89])
    else:
        stack = [cell for r in range(4) for cell in _run(r, [88, 89])]
    assert walked['ports'][-2:] == [stack, _run(4, [88, 89])]
    assert got['applied']['ports'] == walked['ports']
    assert _python(got['screen']) == walked['ports']


def test_a_three_wide_leftover_stacks_two_rows(page):
    """83 wide: 3-wide leftovers, two rows of them (6 cabinets) a port, a
    third would be 9. Rows 0-1, rows 2-3, row 4 alone: 53 ports."""
    got = _both(page, dict(ARMOR_90, columns=83, portNumberOrder='across'))
    walked = got['walked']
    assert walked['auto'] == 53
    left = [80, 81, 82]
    assert walked['ports'][10] == _snake([0, 1], left)
    assert walked['ports'][31] == _snake([2, 3], left)
    assert walked['ports'][-1] == _run(4, left)
    assert got['applied']['ports'] == walked['ports']
    assert _python(got['screen']) == walked['ports']


def test_a_half_row_joins_a_stack_only_where_the_math_fits(page):
    """138 wide: full rows cut 17 x 8 + 2 and the half row 8 x 17 + 2, so
    the half row's leftover sits in the same two columns. Three full
    rows' leftovers (6 cabinets) and the half row's two (one cabinet's
    worth) reserve 384 x 1344 = 516,096 px: one port. With a fourth full
    row the full rows fill the port (8) and the half row's stays alone."""
    three = _both(page, {'columns': 138, 'rows': 4, 'halfRow': 3, 'portNumberOrder': 'down'})
    w = three['walked']
    assert w['ports'][-1] == _snake([0, 1, 2, 3], [136, 137])
    assert three['applied']['ports'] == w['ports']
    assert _python(three['screen']) == w['ports']
    four = _both(page, {'columns': 138, 'rows': 5, 'halfRow': 4, 'portNumberOrder': 'down'})
    w4 = four['walked']
    assert _snake([0, 1, 2, 3], [136, 137]) in w4['ports']
    assert _run(4, [136, 137]) in w4['ports']
    assert four['applied']['ports'] == w4['ports']
    assert _python(four['screen']) == w4['ports']


# ── vertical patterns ──────────────────────────────────────────────────


TALL = {'columns': 5, 'rows': 90, 'cabinet_width': 384, 'cabinet_height': 192,
        'processorType': 'novastar-armor', 'halfRow': None, 'flowPattern': 'tl-v'}


def _col(c, rows):
    return [[r, c] for r in rows]


def _vsnake(cols, rows):
    out = []
    for i, c in enumerate(cols):
        out.extend(_col(c, rows if i % 2 == 0 else list(reversed(rows))))
    return out


@pytest.mark.parametrize("order", ['down', 'across'])
def test_a_vertical_pattern_stacks_column_ends_across_columns(page, order):
    """5 wide x 90 tall of 384 x 192, tl-v: each column cuts 8 x 11 + 2
    (rows 88-89). Columns 0-3's leftovers are one port across the four
    columns, column 4's its own: 57 ports. Down numbers down each column
    (the stacked port after column 0's runs, where its first cabinet is);
    Across numbers the bands, the stacked port in the last band."""
    got = _both(page, dict(TALL, portNumberOrder=order))
    walked = got['walked']
    assert walked['auto'] == 57
    stack = _vsnake([0, 1, 2, 3], [88, 89])
    eights = [list(range(r, r + 8)) for r in range(0, 88, 8)]
    if order == 'down':
        want = [_col(0, rows) for rows in eights] + [stack]
        for c in range(1, 4):
            want += [_col(c, rows) for rows in eights]
        want += [_col(4, rows) for rows in eights] + [_col(4, [88, 89])]
    else:
        want = [_col(c, rows) for rows in eights for c in range(5)]
        want += [stack, _col(4, [88, 89])]
    assert walked['ports'] == want
    assert got['applied']['ports'] == walked['ports']
    assert _python(got['screen']) == walked['ports']


# ── an opened show keeps its drawing ───────────────────────────────────


def test_an_opened_shows_custom_drawing_is_never_rewritten(page):
    """A custom screen drawn under the old cut (four leftover ports of 4
    on rows 0-3, 49 ports) opens through File > Open's own path exactly as
    it was saved: every path as drawn, in the page and on the server, 49
    ports drawn, while Ports required reads the 47 the wall now needs."""
    got = page.evaluate("""async () => {
        const app = window.app;
        const j = (method, url, body) => fetch(url, { method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body) }).then(r => r.json());
        await app._layerSavesSettled();
        // the old Down map: a stack of rows 0-3 per 8 columns with the half
        // row's run under the stack it starts in, then the leftovers row
        // by row
        const paths = {};
        let n = 0;
        const put = cells => { n += 1; paths[n] = cells.map(([row, col]) => ({ row, col })); };
        for (let k = 0; k < 10; k++) {
            for (let r = 0; r < 4; r++) put([...Array(8).keys()].map(i => [r, k * 8 + i]));
            for (let c0 = 0; c0 < 84; c0 += 17) {
                if (c0 >= k * 8 && c0 < k * 8 + 8) {
                    put([...Array(Math.min(17, 84 - c0)).keys()].map(i => [4, c0 + i]));
                }
            }
        }
        for (let r = 0; r < 4; r++) put([80, 81, 82, 83].map(c => [r, c]));
        await fetch('/api/project/new', { method: 'POST' });
        const made = await j('POST', '/api/layer/add', { name: 'Old show', columns: 84, rows: 5,
            cabinet_width: 192, cabinet_height: 384, offset_x: 0, offset_y: 0 });
        await j('PUT', '/api/layer/' + made.id, { halfLastRow: true });
        const show = await j('GET', '/api/project');
        const l = show.layers.find(x => x.id === made.id);
        Object.assign(l, { processorType: 'novastar-coex-1g', bitDepth: 8, frameRate: 60,
            lowLatency: false, portMappingMode: 'organized', portNumberOrder: 'down',
            flowPattern: 'custom', lastFlowPattern: 'tl-h',
            customPortPaths: paths, customPortIndex: n, customPortOverrides: [] });
        show.app_version = '1.6.0-beta.5';
        const saved = JSON.stringify(paths);
        await app._openProjectText(JSON.stringify(show), { source: 'file' });
        await app._layerSavesSettled();
        await new Promise(r => setTimeout(r, 400));
        await app._layerSavesSettled();
        const live = app.project.layers.find(x => x.name === 'Old show');
        app.currentLayer = live;
        app.selectedLayerIds = new Set([live.id]);
        window.canvasRenderer.viewMode = 'data-flow';
        app.updatePortCapacityDisplay();
        const server = (await j('GET', '/api/project')).layers.find(x => x.id === live.id);
        const norm = p => JSON.stringify(Object.keys(p).sort((a, b) => a - b)
            .map(k => [k, p[k].map(e => [e.row, e.col])]));
        return {
            page: norm(live.customPortPaths) === norm(JSON.parse(saved)),
            server: norm(server.customPortPaths || {}) === norm(JSON.parse(saved)),
            drawn: app.getLayerPortsRequired(live),
            shown: document.getElementById('ports-required').textContent.trim(),
        };
    }""")
    assert got == {'page': True, 'server': True, 'drawn': 49, 'shown': '47'}
