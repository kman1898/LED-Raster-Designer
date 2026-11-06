"""The eight Z flow patterns beside the eight snakes (data side).

The owner's ruling (Matt, 2026-11-01): the app's eight patterns are SNAKES,
where every row (horizontal first) or column (vertical first) runs back the
opposite way. Their Z twins, coded `<corner>-<h|v>-z`, start every row or
column again from the SAME side as the first, the way a cable goes back to
the left edge before each new row. Corner and first direction are the
snake's. "we need to make sure you follow the new patterns": every walk
(Organized, Max Capacity, the long-row split, Apply Pattern, the arrows on
the canvas, the numbering) follows the Z order exactly.

The picker is two rows of 8, snakes on top and the Z patterns under them,
each row TL, TR, BL, BR horizontal first, then TL, TR, BL, BR vertical first.

Run locally:
    python -m pytest tests/test_z_flow_patterns.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

import scr_project  # noqa: E402
from test_custom_ports_minimum import HELPERS_JS  # noqa: E402

SNAKES = ['tl-h', 'tr-h', 'bl-h', 'br-h', 'tl-v', 'tr-v', 'bl-v', 'br-v']
ZS = [p + '-z' for p in SNAKES]
ALL = SNAKES + ZS

# Brompton carries 32 cabinets of 128 x 128 a port, so a 4 x 3 grid is one
# port in either mode and the walk order is the whole answer.
SMALL = {'columns': 4, 'rows': 3, 'cabinet_width': 128, 'cabinet_height': 128,
         'processorType': 'brompton'}


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


def expected_order(pattern, rows, cols):
    """The cabinet order, worked from the words of the ruling: lines from
    the start corner, each read from the start side, and on a snake every
    second line read back."""
    corner, direction = pattern.split('-')[:2]
    z = pattern.endswith('-z')
    row_seq = list(range(rows)) if corner[0] == 't' else list(range(rows - 1, -1, -1))
    col_seq = list(range(cols)) if corner[1] == 'l' else list(range(cols - 1, -1, -1))
    if direction == 'h':
        lines = [[[r, c] for c in col_seq] for r in row_seq]
    else:
        lines = [[[r, c] for r in row_seq] for c in col_seq]
    out = []
    for i, line in enumerate(lines):
        out.extend(line[::-1] if (not z and i % 2 == 1) else line)
    return out


def _port_map(page, opts):
    return page.evaluate("""(opts) => {
        const h = window.__cpm;
        const s = h.screen(opts);
        return h.withProject([s], app => h.portMap(app, s));
    }""", opts)


def _cells(got):
    return [p['cells'] for p in got['ports']]


def _flat(got):
    return [c for p in got['ports'] for c in p['cells']]


# ── the walk order on a small grid ─────────────────────────────────────


@pytest.mark.parametrize("mode", ['organized', 'max-capacity'])
@pytest.mark.parametrize("pattern", ALL)
def test_every_pattern_walks_its_grid_in_order(page, pattern, mode):
    got = _port_map(page, dict(SMALL, flowPattern=pattern, portMappingMode=mode))
    assert got['error'] is None
    assert len(got['ports']) == 1
    assert _flat(got) == expected_order(pattern, 3, 4), pattern


@pytest.mark.parametrize("snake", SNAKES)
def test_a_z_differs_from_its_snake_only_on_the_return_lines(page, snake):
    s = _flat(_port_map(page, dict(SMALL, flowPattern=snake)))
    z = _flat(_port_map(page, dict(SMALL, flowPattern=snake + '-z')))
    per = 4 if '-h' in snake else 3
    lines = len(s) // per
    for i in range(lines):
        sl, zl = s[i * per:(i + 1) * per], z[i * per:(i + 1) * per]
        assert zl == (sl[::-1] if i % 2 == 1 else sl), (snake, i)
    # The first line is the snake's, the start corner too.
    assert z[0] == s[0]


@pytest.mark.parametrize("mode", ['organized', 'max-capacity'])
@pytest.mark.parametrize("pattern", ALL)
def test_the_scr_export_walks_every_pattern_the_same(page, pattern, mode):
    js = page.evaluate("""(opts) => {
        const h = window.__cpm;
        const s = h.screen(opts);
        return h.withProject([s], app => ({
            screen: JSON.parse(JSON.stringify(s)), map: h.portMap(app, s) }));
    }""", dict(SMALL, columns=10, rows=8, flowPattern=pattern, portMappingMode=mode))
    items = scr_project.calculate_port_assignments(js['screen'])
    by = {}
    for it in items:
        by.setdefault(it['port'], []).append([it['panel']['row'], it['panel']['col']])
    assert [by[k] for k in sorted(by)] == [p['cells'] for p in js['map']['ports']]


def test_organized_z_runs_every_row_of_a_port_from_the_start_side(page):
    """10 x 8 at 32 a port: whole rows, three a port. On tl-h-z each row
    of every port runs left to right; on the snake the middle row runs
    back."""
    z = _cells(_port_map(page, dict(SMALL, columns=10, rows=8, flowPattern='tl-h-z')))
    assert z == [[[r, c] for r in rows for c in range(10)]
                 for rows in ([0, 1, 2], [3, 4, 5], [6, 7])]
    br = _cells(_port_map(page, dict(SMALL, columns=10, rows=8, flowPattern='br-h-z')))
    assert br[0] == [[r, c] for r in (7, 6, 5) for c in range(9, -1, -1)]


def test_max_capacity_cuts_the_z_walk_where_the_port_fills(page):
    """Max Capacity packs the one continuous Z walk: 32, 32 and 16, cut
    mid-row, every row from the left."""
    got = _port_map(page, dict(SMALL, columns=10, rows=8, flowPattern='tl-h-z',
                               portMappingMode='max-capacity'))
    walk = [[r, c] for r in range(8) for c in range(10)]
    assert _cells(got) == [walk[:32], walk[32:64], walk[64:]]


# ── the long-row split and the Port numbers switch on a Z ──────────────


@pytest.mark.parametrize("snake", ['tl-h', 'tr-h', 'bl-h', 'br-h'])
def test_the_owner_wall_splits_the_same_on_a_z(page, snake):
    """90 x 5 Armor at 8 a port: every cut run reads from the start side on
    a snake already, so its Z twin gives the same 57 ports, 8 x 11 a row
    and four rows' 2-wide leftovers stacked into one port (2026-11-04),
    every run in a row going the same way. Only the stacked port differs:
    the snake runs its second and fourth rows back, the Z reads every row
    from the start side."""
    z = _port_map(page, {'flowPattern': snake + '-z'})
    s = _port_map(page, {'flowPattern': snake})
    assert z['error'] is None and z['auto'] == 57
    zc, sc = _cells(z), _cells(s)
    assert len(zc) == len(sc) == 57
    stacked = [i for i, p in enumerate(zc) if len({r for r, _ in p}) > 1]
    assert len(stacked) == 1
    k = stacked[0]
    assert zc[:k] + zc[k + 1:] == sc[:k] + sc[k + 1:]
    assert sorted(map(tuple, zc[k])) == sorted(map(tuple, sc[k]))
    left = snake.startswith('tl') or snake.startswith('bl')
    for p in zc:
        for row in {r for r, _ in p}:
            cols = [c for r, c in p if r == row]
            assert cols == sorted(cols, reverse=not left), p


def test_down_numbering_on_a_z(page):
    got = _cells(_port_map(page, {'flowPattern': 'tl-h-z', 'portNumberOrder': 'down'}))
    assert got[0] == [[0, c] for c in range(8)]
    assert got[1] == [[1, c] for c in range(8)]
    assert got[5] == [[0, c] for c in range(8, 16)]
    bl = _cells(_port_map(page, {'flowPattern': 'bl-h-z', 'portNumberOrder': 'down'}))
    assert bl[0] == [[4, c] for c in range(8)] and bl[4] == [[0, c] for c in range(8)]
    assert bl[5] == [[4, c] for c in range(8, 16)]


def test_a_tall_z_column_splits_down_the_column(page):
    tall = {'columns': 5, 'rows': 90, 'cabinet_width': 384, 'cabinet_height': 192,
            'flowPattern': 'tl-v-z'}
    got = _cells(_port_map(page, tall))
    # columns 0-3's 2-tall leftovers stack across them (2026-11-04), each
    # column read from the top on a Z
    assert [len(p) for p in got] == [8] * 56 + [2]
    assert [c for p in got[:11] for c in p] == [[r, 0] for r in range(88)]
    assert got[11] == [[r, c] for c in range(4) for r in (88, 89)]
    across = _cells(_port_map(page, dict(tall, portNumberOrder='across')))
    assert across[1] == [[r, 1] for r in range(8)]


# ── Apply Pattern ──────────────────────────────────────────────────────


@pytest.mark.parametrize("mode", ['organized', 'max-capacity'])
@pytest.mark.parametrize("pattern", ['tl-h-z', 'br-v-z'])
def test_apply_pattern_follows_the_z(page, pattern, mode):
    got = page.evaluate("""([pattern, mode, small]) => {
        const h = window.__cpm;
        const opts = Object.assign({}, small, { columns: 10, rows: 8, portMappingMode: mode });
        const s = h.screen(opts);
        s.flowPattern = 'custom';
        const auto = h.screen(Object.assign({}, opts, { flowPattern: pattern }));
        return h.withProject([s], app => {
            app.selectPanelsInRect(s, { x1: 1, y1: 1, x2: 10 * 128 - 1, y2: 8 * 128 - 1 });
            app.applyPatternToSelection(pattern);
            const paths = s.customPortPaths || {};
            const nums = Object.keys(paths).map(Number).sort((a, b) => a - b);
            return { drawn: nums.map(n => paths[n].map(e => [e.row, e.col])),
                     walked: h.portMap(app, auto).ports.map(p => p.cells) };
        });
    }""", [pattern, mode, SMALL])
    assert got['drawn'] == got['walked'], pattern
    assert [c for p in got['drawn'] for c in p][:10] == (
        expected_order(pattern, 8, 10)[:10])


def test_apply_pattern_on_the_owner_wall_with_a_z_and_down(page):
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen({ portNumberOrder: 'down' });
        s.flowPattern = 'custom';
        const auto = h.screen({ portNumberOrder: 'down', flowPattern: 'tl-h-z' });
        return h.withProject([s], app => {
            app.selectPanelsInRect(s, { x1: 1, y1: 1, x2: 90 * 192 - 1, y2: 5 * 384 - 1 });
            app.applyPatternToSelection('tl-h-z');
            const paths = s.customPortPaths || {};
            const nums = Object.keys(paths).map(Number).sort((a, b) => a - b);
            return { drawn: nums.map(n => paths[n].map(e => [e.row, e.col])),
                     walked: h.portMap(app, auto).ports.map(p => p.cells) };
        });
    }""")
    assert len(got['drawn']) == 57
    assert got['drawn'] == got['walked']


# ── the arrows drawn on the canvas ─────────────────────────────────────


ARROWS_JS = """([opts]) => {
    const h = window.__cpm;
    const s = h.screen(opts);
    return h.withProject([s], app => {
        const r = window.canvasRenderer;
        const ctx = r.ctx;
        const segs = [];
        let from = null;
        const origMove = ctx.moveTo, origLine = ctx.lineTo;
        // Only the run lines: drawPort strokes each link as its own
        // moveTo + lineTo pair from one cabinet centre to the next.
        ctx.moveTo = function (x, y) { from = [x, y]; return origMove.call(this, x, y); };
        ctx.lineTo = function (x, y) {
            if (from) segs.push([from, [x, y]]);
            from = null;
            return origLine.call(this, x, y);
        };
        try {
            app.calculatePortAssignments(s);
            r.renderDataFlowArrows(s);
        } finally {
            ctx.moveTo = origMove; ctx.lineTo = origLine;
        }
        const centre = p => [p.x + p.width / 2, p.y + p.height / 2];
        const cellAt = (pt) => {
            const p = s.panels.find(q => Math.abs(centre(q)[0] - pt[0]) <= 1
                                      && Math.abs(centre(q)[1] - pt[1]) <= 1);
            return p ? [p.row, p.col] : null;
        };
        return segs.map(([a, b]) => [cellAt(a), cellAt(b)])
            .filter(([a, b]) => a && b);
    });
}"""


@pytest.mark.parametrize("pattern", ['tl-h-z', 'tr-h-z', 'bl-v-z', 'br-v-z'])
def test_the_canvas_draws_the_z_path_and_no_snake_turn(page, pattern):
    """The run lines join each cabinet to the next in the Z order: one
    diagonal return per line, never a turn down the end of a row."""
    links = page.evaluate(ARROWS_JS, [dict(SMALL, flowPattern=pattern)])
    order = expected_order(pattern, 3, 4)
    want = [[order[i], order[i + 1]] for i in range(len(order) - 1)]
    assert links[:len(want)] == want, (pattern, links)
    horizontal = '-h' in pattern
    for a, b in want:
        # A snake turn joins the two ends of neighbouring lines: same
        # column (horizontal) or same row (vertical), one line apart.
        if horizontal:
            assert not (a[1] == b[1] and abs(a[0] - b[0]) == 1), (a, b)
        else:
            assert not (a[0] == b[0] and abs(a[1] - b[1]) == 1), (a, b)


def test_the_canvas_still_draws_snake_turns_on_a_snake(page):
    links = page.evaluate(ARROWS_JS, [dict(SMALL, flowPattern='tl-h')])
    assert [[0, 3], [1, 3]] in links and [[1, 0], [2, 0]] in links


# ── the picker ─────────────────────────────────────────────────────────


def test_the_picker_is_two_rows_of_eight_snakes_over_z(page):
    page.locator('[data-mode="data-flow"]').click()
    page.wait_for_timeout(300)
    got = page.evaluate("""() => {
        const btns = [...document.querySelectorAll(
            '.flow-pattern-btn:not(.power-flow-pattern-btn)')];
        const grid = btns[0].parentElement;
        const tops = btns.map(b => Math.round(b.getBoundingClientRect().top));
        const g = grid.getBoundingClientRect();
        return {
            patterns: btns.map(b => b.getAttribute('data-pattern')),
            titles: btns.map(b => b.getAttribute('title')),
            rows: [...new Set(tops)].length,
            topRow: tops.slice(0, 8).every(t => t === tops[0]),
            bottomRow: tops.slice(8).every(t => t === tops[8]) && tops[8] > tops[0],
            inside: btns.every(b => b.getBoundingClientRect().right <= g.right + 0.5),
            sameGrid: btns.every(b => b.parentElement === grid),
        };
    }""")
    page.locator('[data-mode="pixel-map"]').click()
    page.wait_for_timeout(300)
    assert got['patterns'] == SNAKES + ZS
    assert got['sameGrid'] and got['rows'] == 2, got
    assert got['topRow'] and got['bottomRow'] and got['inside'], got
    titles = dict(zip(got['patterns'], got['titles']))
    assert titles['tl-h'] == 'Top-left, horizontal first'
    assert titles['tl-h-z'] == 'Top-left, horizontal first, every row starts at the left'
    assert titles['tr-h-z'] == 'Top-right, horizontal first, every row starts at the right'
    assert titles['tl-v-z'] == 'Top-left, vertical first, every column starts at the top'
    assert titles['br-v-z'] == 'Bottom-right, vertical first, every column starts at the bottom'


def test_a_z_tile_sets_the_screen_and_lights_up(page):
    got = page.evaluate("""() => {
        const h = window.__cpm;
        const s = h.screen(Object.assign({}, %s));
        return h.withProject([s], app => {
            app._patternTileTargets = () => ({ change: [s], locked: [] });
            try {
                document.querySelector(
                    '.flow-pattern-btn[data-pattern="bl-v-z"]:not(.power-flow-pattern-btn)').click();
            } finally {
                delete app._patternTileTargets;   // back to the prototype's
            }
            const active = [...document.querySelectorAll(
                '.flow-pattern-btn:not(.power-flow-pattern-btn).active')]
                .map(b => b.getAttribute('data-pattern'));
            return { pattern: s.flowPattern, active };
        });
    }""" % (str(SMALL).replace("'", '"')))
    assert got == {'pattern': 'bl-v-z', 'active': ['bl-v-z']}


def test_preferences_offers_the_sixteen_data_patterns(page):
    """Preferences > Data pattern (setupPreferences, at start-up) offers the
    same sixteen in the picker's order, and Power its sixteen too (the
    power Z patterns, 2026-11-01)."""
    got = page.evaluate("""() => {
        const read = id => [...document.getElementById(id).children]
            .map(b => b.getAttribute('data-pattern'));
        const z = document.querySelector(
            '#pref-data-flow-pattern-grid [data-pattern="tl-h-z"] path');
        return { data: read('pref-data-flow-pattern-grid'),
                 power: read('pref-power-flow-pattern-grid'),
                 zPath: z ? z.getAttribute('d') : null };
    }""")
    assert got['data'] == SNAKES + ZS
    assert got['power'] == SNAKES + ZS
    assert got['zPath'] == 'M 4 4 L 28 4 L 4 16 L 28 16 L 4 28 L 22 28'


def test_an_unknown_pattern_still_walks_as_it_did(page):
    """An old show's odd code is no Z: it walks the way it always has."""
    odd = _flat(_port_map(page, dict(SMALL, flowPattern='tl-h-x')))
    assert odd == expected_order('tl-h', 3, 4)
