"""Screen groups (v0.11.0) - cabinet IDs that run across the whole group.

A group is ONE screen built from more than one layer, because the per-layer
grid is uniform: a wall of 1m JP5 cabinets AND 0.5m standard cabinets has to be
two layers. Cabinet IDs were pure per-layer grid indices, so the second member
restarted at A1 / 1 and one wall carried two cabinets labelled A1 - a tech
reading the map could not tell them apart.

The IDs are now derived from the cabinet's POSITION on the wall, pooled across
every member: the column letter is the rank of that cabinet's column among the
group's distinct column positions, and the sequential number is reading order
over the whole wall. Someone standing in front of the wall counting cabinets
arrives at the label the map shows, and the member boundaries are invisible.

Everything runs against SYNTHETIC projects: window.app.project is swapped for a
hand-built one inside a single page.evaluate and restored in a finally, so
nothing leaks into the session-shared page.

Labels are asserted by recording every string the renderer draws (ctx.fillText
is wrapped for the duration of one call) - never by inspecting style.

Run locally:
    python -m pytest tests/test_screen_groups_numbering.py -v --browser chromium
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


HELPERS_JS = """
window.__gn = {
    // A screen the way create_layer builds one, with a full grid of panels.
    // `states` marks individual cells: {'0,1': {hidden: true}}.
    screen(opts) {
        const o = Object.assign({
            id: 1, name: 'S', type: 'screen', visible: true,
            canvas_id: 'c1',
            columns: 2, rows: 2,
            cabinet_width: 128, cabinet_height: 128,
            panel_width_mm: 500, panel_height_mm: 500,
            offset_x: 0, offset_y: 0,
            panel_weight: 20, weight_unit: 'kg',
            panelWatts: 200, powerVoltage: 208, powerAmperage: 20,
            processorType: 'brompton', bitDepth: 8, frameRate: 60,
            color1: { r: 64, g: 70, b: 128 }, color2: { r: 149, g: 156, b: 184 },
            show_numbers: true, number_size: 30,
            cabinetIdStyle: 'column-row', cabinetIdPosition: 'center',
            cabinetIdColor: '#ffffff',
            show_panel_borders: false, panel_border_width: 2,
            border_color: '#ffffff', rotation: 0,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-h', powerOrganized: true, powerMaximize: false,
        }, opts || {});
        const states = o.states || {};
        const panels = [];
        // Same order and the same numbering rule as _build_panels: row-major,
        // and EVERY grid cell takes a number, hidden and blank included.
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                const st = states[r + ',' + c] || {};
                panels.push({
                    id: r * o.columns + c + 1, number: r * o.columns + c + 1,
                    row: r, col: c,
                    x: o.offset_x + c * o.cabinet_width,
                    y: o.offset_y + r * o.cabinet_height,
                    width: o.cabinet_width, height: o.cabinet_height,
                    hidden: !!st.hidden, blank: !!st.blank, halfTile: 'none',
                    is_color1: (r + c) % 2 === 0,
                });
            }
        }
        delete o.states;
        o.panels = panels;
        return o;
    },

    project(layers, groups) {
        return {
            layers: layers,
            groups: groups || [],
            canvases: [{
                id: 'c1', name: 'Canvas 1',
                workspace_x: 0, workspace_y: 0,
                show_workspace_x: 0, show_workspace_y: 0,
                raster_width: 8192, raster_height: 8192,
                show_raster_width: 8192, show_raster_height: 8192,
                color: '#ff0000', visible: true,
            }],
            active_canvas_id: 'c1',
        };
    },

    group(layers, opts) {
        return Object.assign({
            id: 'g1', name: 'Main Wall', layer_ids: layers.map(l => l.id),
        }, opts || {});
    },

    // Swap in a synthetic project, run fn, put everything back no matter what
    // fn does. Cabinet ID is the view these labels live in.
    withProject(layers, groups, fn) {
        const app = window.app;
        const r = window.canvasRenderer;
        const saved = {
            project: app.project,
            currentLayer: app.currentLayer,
            selectedLayerIds: app.selectedLayerIds,
            updateLayers: app.updateLayers,
            renderLayers: app.renderLayers,
            loadLayerToInputs: app.loadLayerToInputs,
            saveClientSideProperties: app.saveClientSideProperties,
            viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
        };
        app.updateLayers = () => {};
        app.renderLayers = () => {};
        app.loadLayerToInputs = () => {};
        app.saveClientSideProperties = () => {};
        app.project = this.project(layers, groups);
        app.currentLayer = null;
        app.selectedLayerIds = new Set();
        r.viewMode = 'cabinet-id';
        r.zoom = 1; r.panX = 0; r.panY = 0;
        try {
            return fn();
        } finally {
            app.project = saved.project;
            app.currentLayer = saved.currentLayer;
            app.selectedLayerIds = saved.selectedLayerIds;
            app.updateLayers = saved.updateLayers;
            app.renderLayers = saved.renderLayers;
            app.loadLayerToInputs = saved.loadLayerToInputs;
            app.saveClientSideProperties = saved.saveClientSideProperties;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
            // Redraw the restored project, but never let THAT be what a test
            // reports: the page is session-shared, so the live project here is
            // whatever earlier test modules left on the server, and a redraw
            // of it failing says nothing about the numbering under test.
            try { r.render(); } catch (e) { /* restored state is what matters */ }
        }
    },

    // Every string one layer's cabinet IDs draw, in draw order. A full frame
    // runs first so the renderer's raster bounds are the ones a real Cabinet
    // ID frame uses; the IDs are then captured on their own so the screen
    // name and info bar cannot be mistaken for one.
    ids(layer) {
        const r = window.canvasRenderer;
        r.render();
        const ctx = r.ctx;
        const original = ctx.fillText;
        const texts = [];
        ctx.fillText = function (t, x, y, w) {
            texts.push(String(t));
            return original.call(ctx, t, x, y, w);
        };
        try { r.renderCabinetIDNumbers(layer); } finally { ctx.fillText = original; }
        return texts;
    },

    // Every string drawn in one real frame, in draw order.
    drawn() {
        const r = window.canvasRenderer;
        const ctx = r.ctx;
        const original = ctx.fillText;
        const texts = [];
        ctx.fillText = function (t, x, y, w) {
            texts.push(String(t));
            return original.call(ctx, t, x, y, w);
        };
        try { r.render(); } finally { ctx.fillText = original; }
        return texts;
    },

    // The IDs of every layer in the project, keyed by layer id.
    allIds() {
        const out = {};
        window.app.project.layers.forEach(l => { out[l.id] = this.ids(l); });
        return out;
    },
};
"""


# ── The mixed wall this feature exists for ────────────────────────────────
# 4 x 2 of 1m JP5 (128 px cabinets) with an 8 x 2 strip of 0.5m panels (64 px)
# hung underneath. 512 x 256 + 512 x 128 = one 512 x 384 wall.

STACKED_WALL_JS = """
    const jp5 = gn.screen({
        id: 1, name: 'JP5', columns: 4, rows: 2,
        cabinet_width: 128, cabinet_height: 128,
        cabinetIdStyle: STYLE,
    });
    const half = gn.screen({
        id: 2, name: 'Half Panels', columns: 8, rows: 2,
        cabinet_width: 64, cabinet_height: 64,
        offset_y: 256,
        cabinetIdStyle: STYLE,
        states: STATES,
    });
"""


def _stacked(page, style, grouped=True, states='{}'):
    """The mixed wall's IDs, keyed by layer id, grouped or not."""
    body = STACKED_WALL_JS.replace('STYLE', repr(style).replace("'", '"')) \
                          .replace('STATES', states)
    return page.evaluate("""() => {
        const gn = window.__gn;
        %s
        const groups = [];
        if (%s) {
            jp5.group_id = 'g1';
            half.group_id = 'g1';
            groups.push(gn.group([jp5, half]));
        }
        return gn.withProject([jp5, half], groups, () => gn.allIds());
    }""" % (body, 'true' if grouped else 'false'))


# The pooled column positions of that wall are every distinct cabinet edge:
# 0, 64, 128, 192, 256, 320, 384, 448 -> A..H. The 128 px member's own columns
# land on 0, 128, 256, 384, so its letters are A, C, E, G.
JP5_COLUMN_ROW = ['A1', 'C1', 'E1', 'G1', 'A2', 'C2', 'E2', 'G2']
HALF_COLUMN_ROW = (['A3', 'B3', 'C3', 'D3', 'E3', 'F3', 'G3', 'H3']
                   + ['A4', 'B4', 'C4', 'D4', 'E4', 'F4', 'G4', 'H4'])


# ── Uniqueness: the whole point ───────────────────────────────────────────

@pytest.mark.parametrize('style', ['column-row', 'row-column', 'row-col',
                                   'sequential'])
def test_a_grouped_wall_never_labels_two_cabinets_the_same(page, style):
    """Every cabinet on the wall has a distinct ID, in every ID style."""
    ids = _stacked(page, style)
    labels = ids['1'] + ids['2']
    assert len(labels) == 24, labels
    assert len(set(labels)) == len(labels), \
        f'{style}: duplicate IDs {sorted(l for l in labels if labels.count(l) > 1)}'


@pytest.mark.parametrize('style', ['column-row', 'row-column', 'row-col',
                                   'sequential'])
def test_the_same_wall_ungrouped_still_collides(page, style):
    """The bug this fixes, pinned: ungrouped, the two members share IDs."""
    ids = _stacked(page, style, grouped=False)
    labels = ids['1'] + ids['2']
    assert len(set(labels)) < len(labels), \
        f'{style}: ungrouped members no longer collide - is the plan leaking?'


# ── Positions on the wall, not per-member grid indices ────────────────────

def test_column_row_ids_rank_columns_across_the_whole_wall(page):
    """A 1m cabinet's letter is its place on the WALL, so it skips.

    Pooled columns are every distinct cabinet edge (0, 64, 128 ... 448), so
    the 0.5m strip reads A..H and the 1m member above it reads A, C, E, G -
    the letters count places on the wall, which is what someone counting
    cabinets across it counts.
    """
    ids = _stacked(page, 'column-row')
    assert ids['1'] == JP5_COLUMN_ROW, ids['1']
    assert ids['2'] == HALF_COLUMN_ROW, ids['2']


def test_row_numbers_continue_down_the_wall(page):
    """The strip's rows are 3 and 4, not a second member's 1 and 2."""
    ids = _stacked(page, 'column-row')
    assert all(label.endswith(('1', '2')) for label in ids['1']), ids['1']
    assert all(label.endswith(('3', '4')) for label in ids['2']), ids['2']


def test_row_column_style_ranks_rows_across_the_whole_wall(page):
    """Letter = row rank on the wall, number = column rank on the wall."""
    ids = _stacked(page, 'row-column')
    assert ids['1'] == ['A1', 'A3', 'A5', 'A7', 'B1', 'B3', 'B5', 'B7'], ids['1']
    assert ids['2'][:8] == ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8'], ids['2']
    assert ids['2'][8:] == ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'D8'], ids['2']


def test_row_col_style_ranks_both_across_the_whole_wall(page):
    """Comma notation, same ranks."""
    ids = _stacked(page, 'row-col')
    assert ids['1'] == ['1,1', '1,3', '1,5', '1,7',
                        '2,1', '2,3', '2,5', '2,7'], ids['1']
    assert ids['2'][:8] == ['3,1', '3,2', '3,3', '3,4',
                            '3,5', '3,6', '3,7', '3,8'], ids['2']
    assert ids['2'][8:] == ['4,1', '4,2', '4,3', '4,4',
                            '4,5', '4,6', '4,7', '4,8'], ids['2']


def test_sequential_ids_read_across_the_wall_not_member_by_member(page):
    """1..24 in reading order over the wall - the strip picks up at 9."""
    ids = _stacked(page, 'sequential')
    assert ids['1'] == ['1', '2', '3', '4', '5', '6', '7', '8'], ids['1']
    assert ids['2'] == [str(n) for n in range(9, 25)], ids['2']


def test_sequential_ids_restart_per_member_when_ungrouped(page):
    """The before picture: two members, two runs of numbers."""
    ids = _stacked(page, 'sequential', grouped=False)
    assert ids['1'] == ['1', '2', '3', '4', '5', '6', '7', '8'], ids['1']
    assert ids['2'] == [str(n) for n in range(1, 17)], ids['2']


# ── Any number of members, any number of groups ───────────────────────────

THREE_MEMBER_JS = """
    const a = gn.screen({
        id: 1, name: 'A', columns: 2, rows: 2,
        cabinet_width: 128, cabinet_height: 128, cabinetIdStyle: STYLE,
    });
    const b = gn.screen({
        id: 2, name: 'B', columns: 2, rows: 2,
        cabinet_width: 128, cabinet_height: 128, offset_x: 256,
        cabinetIdStyle: STYLE,
    });
    const c = gn.screen({
        id: 3, name: 'C', columns: 4, rows: 4,
        cabinet_width: 64, cabinet_height: 64, offset_x: 512,
        cabinetIdStyle: STYLE,
    });
"""


def _three_members(page, style):
    body = THREE_MEMBER_JS.replace('STYLE', repr(style).replace("'", '"'))
    return page.evaluate("""() => {
        const gn = window.__gn;
        %s
        [a, b, c].forEach(l => { l.group_id = 'g1'; });
        return gn.withProject([a, b, c], [gn.group([a, b, c])],
                              () => gn.allIds());
    }""" % body)


def test_a_three_member_group_pools_every_members_positions(page):
    """Three members, two cabinet sizes, one continuous set of IDs.

    Two 1m screens side by side (columns at x = 0, 128 and 256, 384) with a
    0.5m block beside them (512, 576, 640, 704): eight distinct columns on the
    wall, so A..H runs straight through all three members.
    """
    ids = _three_members(page, 'column-row')
    assert ids['1'] == ['A1', 'B1', 'A3', 'B3'], ids['1']
    assert ids['2'] == ['C1', 'D1', 'C3', 'D3'], ids['2']
    assert ids['3'] == ['E1', 'F1', 'G1', 'H1', 'E2', 'F2', 'G2', 'H2',
                        'E3', 'F3', 'G3', 'H3', 'E4', 'F4', 'G4', 'H4'], ids['3']
    labels = ids['1'] + ids['2'] + ids['3']
    assert len(set(labels)) == 24, labels


def test_three_members_number_sequentially_in_wall_reading_order(page):
    """Left to right along each band of the wall, top band first."""
    ids = _three_members(page, 'sequential')
    # Top band (y = 0): A's two, B's two, then C's four.
    assert ids['1'][:2] == ['1', '2'] and ids['2'][:2] == ['3', '4']
    assert ids['3'][:4] == ['5', '6', '7', '8'], ids['3']
    # y = 64 exists only in the 0.5m member.
    assert ids['3'][4:8] == ['9', '10', '11', '12'], ids['3']
    # y = 128 is the 1m members' second row plus the 0.5m member's third.
    assert ids['1'][2:] == ['13', '14'] and ids['2'][2:] == ['15', '16']
    assert ids['3'][8:12] == ['17', '18', '19', '20'], ids['3']
    assert ids['3'][12:] == ['21', '22', '23', '24'], ids['3']
    labels = ids['1'] + ids['2'] + ids['3']
    assert sorted(int(n) for n in labels) == list(range(1, 25)), labels


def test_two_groups_number_independently(page):
    """A second group on the same canvas starts its own wall at A1."""
    ids = page.evaluate("""() => {
        const gn = window.__gn;
        const a = gn.screen({ id: 1, name: 'A', columns: 2, rows: 2,
                              group_id: 'g1' });
        const b = gn.screen({ id: 2, name: 'B', columns: 4, rows: 2,
                              cabinet_width: 64, cabinet_height: 64,
                              offset_y: 256, group_id: 'g1' });
        const c = gn.screen({ id: 3, name: 'C', columns: 2, rows: 2,
                              offset_x: 4000, group_id: 'g2' });
        const d = gn.screen({ id: 4, name: 'D', columns: 4, rows: 2,
                              cabinet_width: 64, cabinet_height: 64,
                              offset_x: 4000, offset_y: 256, group_id: 'g2' });
        const g1 = gn.group([a, b]);
        const g2 = gn.group([c, d], { id: 'g2', name: 'Second Wall' });
        return gn.withProject([a, b, c, d], [g1, g2], () => gn.allIds());
    }""")
    # Each group ranks only its own members' positions, so both walls start
    # at A1 and neither one's letters are pushed along by the other.
    assert ids['1'] == ['A1', 'C1', 'A2', 'C2'], ids['1']
    assert ids['3'] == ['A1', 'C1', 'A2', 'C2'], ids['3']
    assert ids['2'] == ['A3', 'B3', 'C3', 'D3', 'A4', 'B4', 'C4', 'D4'], ids['2']
    assert ids['4'] == ids['2']


# ── Hidden and blank cabinets behave exactly as they did ──────────────────

def test_a_hidden_cabinet_draws_no_id_but_still_consumes_its_number(page):
    """Hiding a cabinet must not renumber the wall around it.

    That is today's per-layer rule (panel.number counts every grid cell,
    hidden or not, and the label loop skips hidden ones), carried over to the
    group unchanged.
    """
    before = _stacked(page, 'sequential')
    after = _stacked(page, 'sequential', states="{'0,0': {hidden: true}}")
    assert before['1'] == after['1'], 'hiding one member cabinet moved another member'
    # 9 was the hidden cabinet's number; every other number is untouched.
    assert '9' in before['2'] and '9' not in after['2']
    assert after['2'] == [n for n in before['2'] if n != '9'], after['2']


def test_a_hidden_cabinet_still_holds_its_column_letter(page):
    """Its column is still a place on the wall, so the letters do not shift."""
    after = _stacked(page, 'column-row', states="{'0,0': {hidden: true}}")
    assert after['2'] == [l for l in HALF_COLUMN_ROW if l != 'A3'], after['2']
    assert after['1'] == JP5_COLUMN_ROW, after['1']


def test_a_blank_cabinet_is_still_labelled(page):
    """Blank is a hole in the wall, not a missing slot - it keeps its ID."""
    after = _stacked(page, 'column-row', states="{'0,1': {blank: true}}")
    assert after['2'] == HALF_COLUMN_ROW, after['2']
    seq = _stacked(page, 'sequential', states="{'0,1': {blank: true}}")
    assert seq['2'] == [str(n) for n in range(9, 25)], seq['2']


# ── Ungrouped layers are byte-identical ───────────────────────────────────

# A lone screen with one hidden and one blank cabinet, in each style, as the
# per-layer grid-index rules have always drawn it. Pinned here so any drift in
# the ungrouped path fails loudly.
SOLO_EXPECTED = {
    'column-row': ['A1', 'C1', 'A2', 'B2', 'C2'],
    'row-column': ['A1', 'A3', 'B1', 'B2', 'B3'],
    'row-col': ['1,1', '1,3', '2,1', '2,2', '2,3'],
    'sequential': ['1', '3', '4', '5', '6'],
}


def _solo_ids(page, style, beside_a_group):
    return page.evaluate("""() => {
        const gn = window.__gn;
        const solo = gn.screen({
            id: 9, name: 'Solo', columns: 3, rows: 2,
            cabinet_width: 128, cabinet_height: 128,
            cabinetIdStyle: %s,
            states: { '0,1': { hidden: true }, '1,0': { blank: true } },
        });
        const layers = [solo];
        const groups = [];
        if (%s) {
            const jp5 = gn.screen({ id: 1, name: 'JP5', columns: 4, rows: 2,
                                    offset_y: 2000, group_id: 'g1',
                                    cabinetIdStyle: %s });
            const half = gn.screen({ id: 2, name: 'Half', columns: 8, rows: 2,
                                     cabinet_width: 64, cabinet_height: 64,
                                     offset_y: 2256, group_id: 'g1',
                                     cabinetIdStyle: %s });
            layers.push(jp5, half);
            groups.push(gn.group([jp5, half]));
        }
        return gn.withProject(layers, groups, () => gn.ids(solo));
    }""" % (repr(style).replace("'", '"'),
            'true' if beside_a_group else 'false',
            repr(style).replace("'", '"'),
            repr(style).replace("'", '"')))


@pytest.mark.parametrize('style', ['column-row', 'row-column', 'row-col',
                                   'sequential'])
def test_a_lone_screens_ids_are_exactly_what_they_always_were(page, style):
    """The regression guard: no group, no change - per-layer grid indices."""
    assert _solo_ids(page, style, beside_a_group=False) == SOLO_EXPECTED[style]


@pytest.mark.parametrize('style', ['column-row', 'row-column', 'row-col',
                                   'sequential'])
def test_a_group_on_the_same_canvas_does_not_touch_a_lone_screen(page, style):
    """A grouped wall beside it changes nothing about its IDs."""
    alone = _solo_ids(page, style, beside_a_group=False)
    beside = _solo_ids(page, style, beside_a_group=True)
    assert beside == alone == SOLO_EXPECTED[style], (alone, beside)


@pytest.mark.parametrize('style', ['column-row', 'row-column', 'row-col',
                                   'sequential'])
def test_a_group_of_one_matches_a_lone_layer_exactly(page, style):
    """Nothing to run across: a one-member group keeps its own grid indices."""
    grouped = page.evaluate("""() => {
        const gn = window.__gn;
        const only = gn.screen({
            id: 9, name: 'Solo', columns: 3, rows: 2,
            cabinet_width: 128, cabinet_height: 128,
            cabinetIdStyle: %s, group_id: 'g1',
            states: { '0,1': { hidden: true }, '1,0': { blank: true } },
        });
        return gn.withProject([only], [gn.group([only])], () => gn.ids(only));
    }""" % repr(style).replace("'", '"'))
    assert grouped == SOLO_EXPECTED[style], grouped


# ── The uniqueness safety net ─────────────────────────────────────────────

def test_overlapping_members_fall_back_to_the_walls_sequential_numbers(page):
    """Two cabinets can only share a column AND a row rank if they overlap.

    A grid style cannot label that group uniquely, so the whole group drops to
    the wall's sequential numbers rather than drawing two A1s.
    """
    ids = page.evaluate("""() => {
        const gn = window.__gn;
        const a = gn.screen({ id: 1, name: 'A', columns: 2, rows: 2,
                              group_id: 'g1' });
        const b = gn.screen({ id: 2, name: 'B', columns: 2, rows: 2,
                              group_id: 'g1' });   // exactly on top of A
        return gn.withProject([a, b], [gn.group([a, b])], () => gn.allIds());
    }""")
    labels = ids['1'] + ids['2']
    assert sorted(int(n) for n in labels) == list(range(1, 9)), labels
    assert not any(l[0].isalpha() for l in labels), labels


def test_members_that_disagree_on_the_id_style_use_the_first_members(page):
    """One wall, one style - the same rule the group label follows.

    Two styles on one wall would put a column-row A1 next to a row-column A1.
    """
    ids = page.evaluate("""() => {
        const gn = window.__gn;
        const a = gn.screen({ id: 1, name: 'A', columns: 2, rows: 2,
                              cabinetIdStyle: 'column-row', group_id: 'g1' });
        const b = gn.screen({ id: 2, name: 'B', columns: 2, rows: 2,
                              offset_y: 256,
                              cabinetIdStyle: 'row-col', group_id: 'g1' });
        return gn.withProject([a, b], [gn.group([a, b])], () => gn.allIds());
    }""")
    assert ids['1'] == ['A1', 'B1', 'A2', 'B2'], ids['1']
    assert ids['2'] == ['A3', 'B3', 'A4', 'B4'], ids['2']


# ── ...and it all happens in a real frame ─────────────────────────────────

def test_the_group_ids_are_what_a_real_cabinet_id_frame_draws(page):
    """Not just the helper: a full render draws the wall-wide IDs."""
    texts = page.evaluate("""() => {
        const gn = window.__gn;
        const jp5 = gn.screen({ id: 1, name: 'JP5', columns: 4, rows: 2,
                                group_id: 'g1' });
        const half = gn.screen({ id: 2, name: 'Half', columns: 8, rows: 2,
                                 cabinet_width: 64, cabinet_height: 64,
                                 offset_y: 256, group_id: 'g1' });
        return gn.withProject([jp5, half], [gn.group([jp5, half])],
                              () => gn.drawn());
    }""")
    for label in JP5_COLUMN_ROW + HALF_COLUMN_ROW:
        assert texts.count(label) == 1, f'{label} drawn {texts.count(label)} times'
