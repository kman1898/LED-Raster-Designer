"""The Rigging tab: bar-fitting math (rigging-math.js) and the per-screen fields.

rigging-math.js is plain functions with no DOM, so it runs under node here;
the tests skip where node is not installed.
"""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATH_JS = os.path.join(ROOT, 'src', 'static', 'js', 'rigging-math.js')

needs_node = pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')


def _fit(total, sizes):
    script = (f"const R = require({json.dumps(MATH_JS)});"
              f"console.log(JSON.stringify(R.fitBars({json.dumps(total)}, {json.dumps(sizes)})));")
    out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@needs_node
@pytest.mark.parametrize('total, sizes, expected', [
    (8, [1, 2, 3, 4, 5, 6], [4, 4]),        # a mirror beats the shorter 6 + 2
    (8, [2, 3, 4], [4, 4]),
    (7, [1, 2, 3, 4, 5, 6], [2, 3, 2]),     # a mirror beats the shorter 4 + 3, and takes no single
    (9, [1, 2], [2, 2, 1, 2, 2]),           # one single, dead centre: a mirror at no extra singles
    (21, [1, 2], [2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2]),
    (12, [2, 3], [3, 3, 3, 3]),
    (10, [3, 4], [3, 4, 3]),                # lone bar sits in the middle
    (13, [6, 1], [6, 1, 6]),
    (15, [1, 2, 3, 4, 5, 6], [6, 3, 6]),
])
def test_fit_bars_prefers_the_fewest_bars_in_a_mirror(total, sizes, expected):
    assert _fit(total, sizes) == expected


@needs_node
@pytest.mark.parametrize('total, sizes, expected', [
    (7, [3, 4, 5, 6], [4, 3]),              # no mirror exists: fewest bars, as balanced as it gets
    (8, [3, 5], [5, 3]),
    # a mirror of 19 needs three singles (both ends and the middle): never
    # worth it. One single on the left, then doubles.
    (19, [1, 2], [1, 2, 2, 2, 2, 2, 2, 2, 2, 2]),
    (7, [1, 2], [1, 2, 2, 2]),
    (11, [1, 2], [1, 2, 2, 2, 2, 2]),
])
def test_fit_bars_falls_back_when_no_mirror_exists(total, sizes, expected):
    assert _fit(total, sizes) == expected
    assert expected != expected[::-1]


@needs_node
@pytest.mark.parametrize('total, sizes', [
    (5, [2, 4]),     # no exact combination
    (8, [6]),
    (8, []),         # nothing highlighted
    (0, [3]),
    (-4, [2]),
])
def test_fit_bars_returns_null_when_it_cannot_fit(total, sizes):
    assert _fit(total, sizes) is None


@needs_node
@pytest.mark.parametrize('bars, index, delta, expected', [
    ([1, 2, 2, 2], 0, 0, [1, 2, 2, 2]),        # not moved
    ([1, 2, 2, 2], 0, 3, [2, 1, 2, 2]),        # right edge passes the next bar's middle
    ([1, 2, 2, 2], 0, 6, [2, 2, 2, 1]),        # all the way right
    ([1, 2, 2, 2], 3, -5, [2, 1, 2, 2]),       # a bar can reach the left end
    ([1, 2, 2, 2], 3, -0.4, [1, 2, 2, 2]),     # a nudge changes nothing
    ([4, 2, 3], 1, 2, [4, 3, 2]),
    ([4, 2, 3], 0, 9, [2, 3, 4]),              # a long bar reaches the far end
    ([3], 0, 5, [3]),
])
def test_move_bar_reorders_without_resizing(bars, index, delta, expected):
    script = (f"const R = require({json.dumps(MATH_JS)});"
              f"console.log(JSON.stringify(R.moveBar({json.dumps(bars)}, {index}, {delta})));")
    out = json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)
    assert out == expected
    assert sorted(out) == sorted(bars)         # same bars, same total: the wall stays covered


@needs_node
@pytest.mark.parametrize('bars, boundary, delta, expected', [
    ([3, 3], 0, 1, [4, 2]),                  # widen the left bar, the right gives a panel up
    ([3, 3], 0, -1, [2, 4]),                 # drag the same edge left: the right bar grows
    ([3, 3], 0, 1.4, [4, 2]),                # whole panels only
    ([3, 3], 0, 0.4, [3, 3]),                # a nudge changes nothing
    ([2, 4], 0, 9, [4, 2]),                  # stops at a quad on the growing bar
    ([2, 2], 0, 5, [3, 1]),                  # the shrinking bar never goes under 1
    ([4, 2, 4], 1, 1, [4, 3, 3]),            # only the two bars at that edge change
    ([4, 2, 4], 1, -9, [4, 2, 4]),           # the right bar is a quad already: it can take no more
    ([4, 4], 0, 1, [4, 4]),                  # both at the limit: nothing to give
    ([8], 0, 1, [8]),                        # one bar has no edge to drag
])
def test_resize_boundary_trades_panels_between_neighbours(bars, boundary, delta, expected):
    script = (f"const R = require({json.dumps(MATH_JS)});"
              f"console.log(JSON.stringify(R.resizeBoundary({json.dumps(bars)}, {boundary}, {delta})));")
    out = json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)
    assert out == expected
    assert sum(out) == sum(bars)             # the wall stays covered


def _node(expr):
    script = f"const R = require({json.dumps(MATH_JS)}); console.log(JSON.stringify({expr}));"
    out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@needs_node
def test_tally_counts_bars_across_screens():
    assert _node('R.tally([[4, 4], [6, 2, 2], null, [4]])') == {'total': 6, 'bySize': {'4': 3, '6': 1, '2': 2}}
    assert _node('R.tally([])') == {'total': 0, 'bySize': {}}
    assert _node('R.tally([[0, -1, 2.5, "x"]])') == {'total': 0, 'bySize': {}}


@needs_node
def test_bar_names_use_single_double_triple_quad():
    assert [_node(f'R.sizeWord({n})') for n in range(1, 7)] == ['Single', 'Double', 'Triple', 'Quad', '5-way', '6-way']


@needs_node
def test_bar_name_is_the_pull_list_type():
    assert _node('R.barName(4)') == 'Header Bar - Quad'
    assert _node("R.barName(2, 'footer')") == 'Footer Bar - Double'


@needs_node
@pytest.mark.parametrize('rotation, panels', [(0, 12), (90, 6), (180, 12), (270, 6), (-90, 6), (450, 6), (None, 12)])
def test_the_wall_is_its_rows_wide_once_turned_a_quarter(rotation, panels):
    assert _node(f"R.wallPanels(12, 6, {json.dumps(rotation)})") == panels


@needs_node
@pytest.mark.parametrize('bars, width, fits', [
    ([], 16, True),             # no bars are no claim on the wall
    ([2, 2, 2], 6, True),
    ([2, 2, 2], 8, False),      # short
    ([2, 2, 2], 4, False),      # long
])
def test_bars_fit_only_when_they_add_up_to_the_wall(bars, width, fits):
    assert _node(f"R.barsFit({json.dumps(bars)}, {width})") is fits


def test_a_row_that_no_longer_fits_carries_its_note_into_the_workbook():
    openpyxl = pytest.importorskip('openpyxl')
    import io
    import pull_sheet
    note = 'Header bars cover 12 panels, the wall is 16. Press Auto on the Header/Footer tab.'
    pull_list = {'positions': [{'name': 'Wall', 'rows': [
        {'type': 'Header Bar - Double', 'length': 'EA', 'qty': 6, 'label': 'Wall (bars no longer fit)',
         'notes': note, 'side': 'rigging'},
    ]}]}
    xlsx, _warnings = pull_sheet.build_workbook(pull_list, {'project_name': 'Show'})
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    seen = {str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None}
    assert 'Wall (bars no longer fit)' in seen and note in seen


def test_header_bar_rows_reach_the_pull_sheet_workbook():
    """The client's pull list carries one EA row per header bar size; the
    workbook writes it and adds the type to the GEAR LIST like any new gear."""
    openpyxl = pytest.importorskip('openpyxl')
    import io
    import pull_sheet
    pull_list = {'positions': [{'name': 'Wall', 'rows': [
        {'type': 'Header Bar - Quad', 'length': 'EA', 'qty': 2, 'label': 'Wall', 'notes': '', 'side': 'rigging'},
    ]}]}
    xlsx, _warnings = pull_sheet.build_workbook(pull_list, {'project_name': 'Show'})
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    seen = {str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None}
    assert 'Header Bar - Quad' in seen


def test_rigging_fields_save_and_come_back(client):
    """riggingSizes / riggingBars are whitelisted on PUT, so they survive the echo."""
    layer = client.post('/api/layer/add', json={'name': 'Wall', 'columns': 8}).get_json()
    resp = client.put(f"/api/layer/{layer['id']}",
                      json={'riggingSizes': [2, 4], 'riggingBars': [4, 4], 'riggingFooterBars': [2, 2, 4],
                            'riggingColor': '#1e90ff', 'riggingTextColor': '#000000',
                            'showLabelNameRigging': False, 'screenNameSizeRigging': 44,
                            'screenNameOffsetXRigging': 12, 'screenNameOffsetYRigging': -8})
    assert resp.status_code == 200
    echoed = resp.get_json()
    assert echoed['riggingSizes'] == [2, 4]
    assert echoed['riggingBars'] == [4, 4]
    assert echoed['riggingColor'] == '#1e90ff'
    assert echoed['riggingTextColor'] == '#000000'
    assert echoed['riggingFooterBars'] == [2, 2, 4]
    assert echoed['showLabelNameRigging'] is False
    assert echoed['screenNameSizeRigging'] == 44
    assert (echoed['screenNameOffsetXRigging'], echoed['screenNameOffsetYRigging']) == (12, -8)

    project = client.get('/api/project').get_json()
    saved = next(l for l in project['layers'] if l['id'] == layer['id'])
    assert saved['riggingBars'] == [4, 4]


# ── Placed bars: one side, Custom, rows across a group's seams (2026-11-08) ──

def _bars(pairs):
    return json.dumps([{'start': s, 'size': n} for s, n in pairs])


def _pairs(out):
    return [[b['start'], b['size']] for b in out]


@needs_node
@pytest.mark.parametrize('bars, starts, expected', [
    ([2, 4, 3, 3], None, [[0, 2], [2, 4], [6, 3], [9, 3]]),     # an older show: end to end from panel 0
    ([2, 2], [3, 8], [[3, 2], [8, 2]]),                         # a gap, kept by its starts
    ([2, 2], [3], [[0, 2], [2, 2]]),                            # starts that do not match are ignored
    ([2, 2], [3, 1.5], [[0, 2], [2, 2]]),
    ([], None, []),
])
def test_placed_bars_read_older_rows_end_to_end(bars, starts, expected):
    assert _pairs(_node(f"R.placedOf({json.dumps(bars)}, {json.dumps(starts)})")) == expected


@needs_node
def test_a_flush_row_stores_no_starts_and_a_gapped_one_does():
    assert _node(f"R.storeOf({_bars([[0, 2], [2, 4]])})") == {'bars': [2, 4], 'starts': None}
    assert _node(f"R.storeOf({_bars([[6, 3], [0, 2]])})") == {'bars': [2, 3], 'starts': [0, 6]}
    assert _node(f"R.storeOf({_bars([[1, 2], [3, 2]])})") == {'bars': [2, 2], 'starts': [1, 3]}
    assert _node("R.storeOf([])") == {'bars': [], 'starts': None}


@needs_node
def test_a_new_bar_replaces_every_bar_it_overlaps():
    row = _bars([[0, 2], [2, 2], [4, 2], [8, 2]])
    assert _pairs(_node(f"R.placeBars({row}, {_bars([[3, 4]])})")) == [[0, 2], [3, 4], [8, 2]]
    assert _pairs(_node(f"R.placeBars({row}, {_bars([[6, 2]])})")) == [[0, 2], [2, 2], [4, 2], [6, 2], [8, 2]]


@needs_node
@pytest.mark.parametrize('panel, size, width, expected', [
    (3, 2, 12, [[3, 2]]),
    (11, 4, 12, [[8, 4]]),        # moved in just far enough to stay on the wall
    (0, 4, 3, []),                # a bar wider than the row
])
def test_a_click_drops_one_bar_at_the_panel(panel, size, width, expected):
    assert _pairs(_node(f"R.barsForClick({panel}, {size}, {width})")) == expected


@needs_node
@pytest.mark.parametrize('a, b, size, width, expected', [
    (3, 10, 2, 22, [[3, 2], [5, 2], [7, 2], [9, 2]]),     # 8 panels, four doubles
    (3, 9, 2, 22, [[3, 2], [5, 2], [7, 2]]),              # 7 panels: the odd one stays empty
    (10, 3, 4, 22, [[3, 4], [7, 4]]),                     # leftward: laid back from the press
    (10, 4, 4, 22, [[7, 4]]),                             # 7 panels leftward: one quad, ending at 10
    (5, 6, 4, 22, [[5, 4]]),                              # shorter than a bar: a click
    (8, 40, 4, 12, [[8, 4]]),                             # the mouse past the row's end
])
def test_a_drag_lays_whole_bars_along_the_span(a, b, size, width, expected):
    assert _pairs(_node(f"R.barsForDrag({a}, {b}, {size}, {width})")) == expected


@needs_node
def test_the_edge_drag_needs_two_bars_that_touch():
    touching = _bars([[0, 3], [3, 3], [8, 2]])
    assert _pairs(_node(f"R.resizeEdgeAt({touching}, 0, 1)")) == [[0, 4], [4, 2], [8, 2]]
    assert _pairs(_node(f"R.resizeEdgeAt({touching}, 1, 1)")) == [[0, 3], [3, 3], [8, 2]]   # a gap: no edge


@needs_node
def test_a_moved_bar_stays_in_its_block_and_the_gap_stays_put():
    row = _bars([[0, 1], [1, 3], [6, 2], [8, 2]])
    out = _node(f"R.moveInBlock({row}, 0, 9)")
    assert _pairs(out['placed']) == [[0, 3], [3, 1], [6, 2], [8, 2]] and out['index'] == 1


def _rect(i, x, y, w, h, panels):
    return {'id': i, 'x': x, 'y': y, 'w': w, 'h': h, 'panels': panels}


@needs_node
def test_members_edge_to_edge_form_one_row():
    rects = [_rect(2, 2200, 0, 2200, 800, 11), _rect(1, 0, 0, 2200, 800, 11)]
    assert _node(f"R.runsOf({json.dumps(rects)}, 'header')") == [
        {'ids': [1, 2], 'offsets': [0, 11], 'panels': [11, 11], 'width': 22}]


@needs_node
@pytest.mark.parametrize('second, side, runs', [
    (_rect(2, 2400, 0, 2200, 800, 11), 'header', 2),      # a gap between them
    (_rect(2, 2200, 200, 2200, 800, 11), 'header', 2),    # a step: the tops do not line up
    (_rect(2, 2200, 200, 2200, 600, 11), 'footer', 1),    # ... but their bottoms do
    (_rect(2, 2200, 0, 2200, 800, 22), 'header', 2),      # a different panel width
    (_rect(2, 0, 800, 2200, 800, 11), 'header', 2),       # stacked
])
def test_a_gap_a_step_or_a_stack_breaks_the_row(second, side, runs):
    rects = [_rect(1, 0, 0, 2200, 800, 11), second]
    assert len(_node(f"R.runsOf({json.dumps(rects)}, '{side}')")) == runs


@needs_node
def test_a_straddling_bar_is_stored_on_the_member_it_starts_on():
    run = json.dumps({'ids': [1, 2], 'offsets': [0, 11], 'panels': [11, 11], 'width': 22})
    doubles = _bars([[i, 2] for i in range(0, 22, 2)])
    parts = _node(f"R.distribute({run}, {doubles})")
    assert _pairs(parts[0]) == [[i, 2] for i in range(0, 12, 2)]      # the last one runs onto the next
    assert _pairs(parts[1]) == [[i, 2] for i in range(1, 11, 2)]
    assert sum(len(p) for p in parts) == 11                          # each bar once


@needs_node
@pytest.mark.parametrize('bars, width, spans, custom, problem', [
    ([[0, 2], [2, 2]], 4, [[0, 4]], False, None),
    ([[0, 2], [4, 2]], 8, [[0, 8]], False, 'gap'),            # an Auto row covers its wall
    ([[0, 2], [4, 2]], 8, [[0, 8]], True, None),              # a custom row may leave gaps
    ([[6, 4]], 8, [[0, 8]], True, 'past'),                    # but never runs past the edge
    ([[0, 4], [2, 2]], 8, [[0, 8]], True, 'overlap'),
    ([[0, 2], [2, 2]], 8, [[0, 4], [4, 4]], False, None),     # the empty member makes no claim
    ([[0, 2], [2, 2], [4, 2], [6, 2]], 8, [[0, 4], [4, 4]], False, None),
    ([[0, 2], [2, 2], [4, 2]], 8, [[0, 4], [4, 4]], False, 'gap'),
])
def test_what_is_wrong_with_a_row(bars, width, spans, custom, problem):
    got = _node(f"R.rowProblem({_bars(bars)}, {width}, {json.dumps(spans)}, {json.dumps(custom)})")
    if problem is None:
        assert got is None
    else:
        assert got[problem], got


def test_the_new_rigging_fields_save_and_come_back(client):
    layer = client.post('/api/layer/add', json={'name': 'Wall', 'columns': 12}).get_json()
    resp = client.put(f"/api/layer/{layer['id']}",
                      json={'riggingBars': [2, 2], 'riggingBarStarts': [1, 8], 'riggingFooterBars': [],
                            'riggingFooterBarStarts': None, 'riggingSide': 'footer', 'riggingCustom': True})
    assert resp.status_code == 200
    saved = next(l for l in client.get('/api/project').get_json()['layers'] if l['id'] == layer['id'])
    assert saved['riggingBarStarts'] == [1, 8] and saved['riggingFooterBarStarts'] is None
    assert saved['riggingSide'] == 'footer' and saved['riggingCustom'] is True


# ── A copy of one member keeps the bars over it, cut at its edges (2026-11-08) ──

@needs_node
@pytest.mark.parametrize('bars, offset, panels, expected', [
    # 11 doubles across two 11 wide walls: the left keeps 5 and half the straddler
    ([[i, 2] for i in range(0, 22, 2)], 0, 11, [[0, 2], [2, 2], [4, 2], [6, 2], [8, 2], [10, 1]]),
    # the right takes the other half, then its own 5
    ([[i, 2] for i in range(0, 22, 2)], 11, 11, [[0, 1], [1, 2], [3, 2], [5, 2], [7, 2], [9, 2]]),
    ([[8, 4], [12, 4]], 11, 11, [[0, 1], [1, 4]]),              # a gap stays a gap
    ([[0, 4]], 4, 4, []),                                       # nothing over this one
    ([[2, 4]], 0, 8, [[2, 4]]),                                 # a bar on it is untouched
])
def test_clip_to_one_member(bars, offset, panels, expected):
    assert _pairs(_node(f"R.clipTo({_bars(bars)}, {offset}, {panels})")) == expected


def test_the_auto_or_custom_choice_is_saved_with_the_show(client):
    assert client.put('/api/project/rigging-tool', json={'tool': 'custom'}).get_json() == {'riggingTool': 'custom'}
    assert client.get('/api/project').get_json()['riggingTool'] == 'custom'
    # anything else is Auto
    assert client.put('/api/project/rigging-tool', json={'tool': 'hand'}).get_json() == {'riggingTool': 'auto'}
    assert client.get('/api/project').get_json()['riggingTool'] == 'auto'
    assert client.put('/api/project/rigging-tool', json=['custom']).status_code == 400


# ── Corner bars, the owner's rulings of 2026-11-10 ──

@needs_node
def test_the_1_panel_and_2_panel_corner_bars_are_two_parts():
    assert _node("R.cornerName(1)") == 'Header Bar - Corner (1 panel)'
    assert _node("R.cornerName(2, 'footer')") == 'Footer Bar - Corner (2 panel)'
    assert _node("R.cornerWord(2)") == 'Corner (2 panel)'


@needs_node
def test_only_a_90_degree_corner_takes_a_corner_bar():
    corners = [{'at': 2, 'angle': 90}, {'at': 4.5, 'angle': 45}, {'at': 7, 'angle': 89.9}, {'at': 9.5}]
    pieces = _node(f"R.cornerPieces({json.dumps(corners)}, 12)")
    assert [(p['at'], p['start'], p['size']) for p in pieces] == [(2, 1, 1), (9.5, 8, 2)]
    # under 90: the seam at 4.5 breaks at edge 4, the panel at 7 at edges 6 and 7
    assert _node(f"R.cornerBreaks({json.dumps(corners)}, 12)") == [4, 6, 7]
    assert _node(f"R.cornerBreaks({json.dumps(corners)}, 12, true)") == [5, 6, 8]
    # the seam of a corner under 90 is a flat joint; a folded panel's is not
    assert _node(f"R.cornerFlatJoints({json.dumps(corners)}, 12)") == [3]


@needs_node
@pytest.mark.parametrize('breaks, expected', [
    ([3], [[0, 1], [1, 2], [3, 1], [4, 2]]),           # a seam under 90: split at it
    ([2, 3], [[0, 2], [2, 1], [3, 1], [4, 2]]),        # down panel 3: it takes a single
    ([], [[0, 2], [2, 2], [4, 2]]),                    # no corner: as it always was
])
def test_auto_bars_never_cross_a_corner_under_90(breaks, expected):
    got = _pairs(_node(f"R.fitAround(6, [1, 2], [], {json.dumps(breaks)})"))
    assert got == expected
    for start, size in got:
        assert not any(start < e < start + size for e in breaks)


@needs_node
def test_a_bar_across_a_corner_under_90_is_wrong_in_any_row():
    problem = _node(f"R.rowProblem({_bars([[2, 2]])}, 6, [[0, 6]], true, [], [3])")
    assert problem['across'] is True
    assert _node(f"R.rowProblem({_bars([[0, 3], [3, 3]])}, 6, [[0, 6]], false, [], [3])") is None
    # Custom by hand: a drag over the break lays bars on each side of it
    lay = _node(f"R.layAround(0, 5, 2, 6, [], [3])")
    assert _pairs(lay['adds']) == [[0, 2], [3, 2]]
