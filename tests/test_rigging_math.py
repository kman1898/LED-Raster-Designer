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
    ([4, 4], 0, 1, [5, 3]),                  # widen the left bar, the right gives a panel up
    ([4, 4], 0, -1, [3, 5]),                 # drag the same edge left: the right bar grows
    ([4, 4], 0, 1.4, [5, 3]),                # whole panels only
    ([4, 4], 0, 0.4, [4, 4]),                # a nudge changes nothing
    ([4, 4], 0, 9, [6, 2]),                  # stops at 6 on the growing bar
    ([2, 2], 0, 5, [3, 1]),                  # the shrinking bar never goes under 1
    ([5, 2, 5], 1, 1, [5, 3, 4]),            # only the two bars at that edge change
    ([5, 2, 5], 1, -9, [5, 1, 6]),
    ([6, 6], 0, 1, [6, 6]),                  # both at the limit: nothing to give
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
def test_bar_names_use_single_double_triple_then_n_way():
    assert [_node(f'R.sizeWord({n})') for n in range(1, 7)] == ['Single', 'Double', 'Triple', '4-way', '5-way', '6-way']


@needs_node
def test_bar_name_is_the_pull_list_type():
    assert _node('R.barName(4)') == 'Header Bar - 4-way'
    assert _node("R.barName(2, 'footer')") == 'Footer Bar - Double'


def test_header_bar_rows_reach_the_pull_sheet_workbook():
    """The client's pull list carries one EA row per header bar size; the
    workbook writes it and adds the type to the GEAR LIST like any new gear."""
    openpyxl = pytest.importorskip('openpyxl')
    import io
    import pull_sheet
    pull_list = {'positions': [{'name': 'Wall', 'rows': [
        {'type': 'Header Bar - 4-way', 'length': 'EA', 'qty': 2, 'label': 'Wall', 'notes': '', 'side': 'rigging'},
    ]}]}
    xlsx, _warnings = pull_sheet.build_workbook(pull_list, {'project_name': 'Show'})
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    seen = {str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None}
    assert 'Header Bar - 4-way' in seen


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
