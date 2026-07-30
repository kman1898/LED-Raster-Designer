"""Coverage for ``app._compute_panel_contour`` - the polygon that becomes the
Resolume mapping for a non-rectangular screen (``app._resolume_polygon``).

The function used to walk a uniform ``row/col * cabinet_size`` grid, so any
screen with half tiles exported a contour a whole cabinet too tall or too wide
and the Resolume mapping was wrong on a real show. It now traces the union of
the visible panels' REAL rectangles.

Every expected value here is derived from actual ``_build_panels`` output
rather than from hand-rolled index arithmetic, so these tests cannot bake in
the same wrong assumption the bug was made of. The one exception is
``test_plain_rectangular_wall_*``, which pins the literal pre-change output:
those contours ship in existing Resolume mappings and must never move.
"""

import pytest

from app import _build_panels, _compute_panel_contour, _layer_bounds


# ── helpers ───────────────────────────────────────────────────────────────

def _screen(rows, cols, cw=128, ch=128, off_x=0, off_y=0, states=None):
    """Build a screen layer with real panel geometry from _build_panels."""
    layer = {
        'rows': rows, 'columns': cols,
        'cabinet_width': cw, 'cabinet_height': ch,
        'offset_x': off_x, 'offset_y': off_y,
    }
    layer['panels'] = _build_panels(layer, dict(states or {}))
    return layer


def _panel(layer, row, col):
    """The panel dict at (row, col), for deriving expectations from geometry."""
    for p in layer['panels']:
        if p['row'] == row and p['col'] == col:
            return p
    raise AssertionError(f'no panel at row={row} col={col}')


def _left(p):    return int(p['x'])
def _right(p):   return int(p['x'] + p['width'])
def _top(p):     return int(p['y'])
def _bottom(p):  return int(p['y'] + p['height'])


def _assert_axis_aligned_loop(contour):
    """Every segment (including the closing one) is horizontal or vertical,
    has non-zero length, and turns at each vertex."""
    assert len(contour) >= 4, contour
    n = len(contour)
    for i in range(n):
        x1, y1 = contour[i]
        x2, y2 = contour[(i + 1) % n]
        assert (x1 == x2) != (y1 == y2), f'segment {i} not axis-aligned: {(x1, y1)}->{(x2, y2)}'
    assert len(set(contour)) == n, f'repeated vertex in {contour}'


def _visible_bounds(layer):
    """_layer_bounds over only the visible panels - the contour's extremes
    must match this for any shape."""
    vis = [p for p in layer['panels'] if not p.get('hidden')]
    return _layer_bounds({'panels': vis})


def _assert_matches_visible_bounds(layer, contour):
    b = _visible_bounds(layer)
    assert min(x for x, _ in contour) == int(b['x'])
    assert min(y for _, y in contour) == int(b['y'])
    assert max(x for x, _ in contour) == int(b['x'] + b['width'])
    assert max(y for _, y in contour) == int(b['y'] + b['height'])


# ── regression guard: plain rectangular walls must not move ───────────────

# Captured from _compute_panel_contour BEFORE the half-tile fix. These exact
# point sequences are baked into every Resolume mapping already in the field;
# both the order and the direction are load-bearing.
PINNED_RECTANGULAR = [
    # (rows, cols, cab_w, cab_h, off_x, off_y): contour
    ((3, 4, 128, 128, 0, 0), [(512, 0), (0, 0), (0, 384), (512, 384)]),
    ((3, 4, 192, 384, 0, 0), [(768, 0), (0, 0), (0, 1152), (768, 1152)]),
    ((2, 2, 100, 50, 17, 23), [(217, 23), (17, 23), (17, 123), (217, 123)]),
    ((1, 1, 128, 128, 0, 0), [(128, 0), (0, 0), (0, 128), (128, 128)]),
    ((4, 1, 128, 128, 5, 7), [(133, 7), (5, 7), (5, 519), (133, 519)]),
]


@pytest.mark.parametrize('params,expected', PINNED_RECTANGULAR)
def test_plain_rectangular_wall_contour_is_unchanged(params, expected):
    """A plain wall exports byte-identical points to the pre-fix code."""
    rows, cols, cw, ch, off_x, off_y = params
    layer = _screen(rows, cols, cw, ch, off_x, off_y)
    contour = _compute_panel_contour(layer)
    assert contour == expected
    # Byte-identical means ints, not 1.0-style floats: the values go straight
    # into the XML as f'<v x="{x}" y="{y}"/>'.
    assert all(type(v) is int for pt in contour for v in pt)


def test_plain_rectangular_wall_winding_is_unchanged():
    """The documented winding (top-right, left along the top, down the left
    side, right along the bottom) must survive the rewrite."""
    layer = _screen(3, 4, 128, 128)
    tr, tl, bl, br = _compute_panel_contour(layer)
    assert tr == (_right(_panel(layer, 0, 3)), _top(_panel(layer, 0, 0)))
    assert tl == (_left(_panel(layer, 0, 0)), _top(_panel(layer, 0, 0)))
    assert bl == (_left(_panel(layer, 0, 0)), _bottom(_panel(layer, 2, 0)))
    assert br == (_right(_panel(layer, 0, 3)), _bottom(_panel(layer, 2, 0)))
    # Start at the top-right, then travel LEFT along the top edge.
    assert tr[0] > tl[0] and tr[1] == tl[1]


# ── half tiles: the actual bug ────────────────────────────────────────────

def test_bottom_row_all_half_height():
    """A wholly half-height bottom row collapses to half height, so the
    contour's bottom edge sits half a cabinet higher than the old code put it.

    3 rows x 2 cols of 128x128: rows 0-1 are full (128 + 128 = 256), row 2 is
    half (64), so the bottom edge is at 320 - not the 3 * 128 = 384 the old
    index arithmetic produced.
    """
    states = {(2, c): {'halfTile': 'height'} for c in range(2)}
    layer = _screen(3, 2, 128, 128, states=states)

    half = _panel(layer, 2, 0)
    assert (half['height'], half['y']) == (64, 256)   # the row really collapsed
    assert _bottom(half) == 320

    contour = _compute_panel_contour(layer)
    assert contour == [(256, 0), (0, 0), (0, 320), (256, 320)]
    assert max(y for _, y in contour) == _bottom(half) == 320
    assert max(y for _, y in contour) != 3 * 128   # the old, wrong answer
    _assert_axis_aligned_loop(contour)
    _assert_matches_visible_bounds(layer, contour)


def test_last_column_all_half_width():
    """A wholly half-width last column collapses to half width: 128 + 64 = 192,
    not 2 * 128 = 256."""
    states = {(r, 1): {'halfTile': 'width'} for r in range(3)}
    layer = _screen(3, 2, 128, 128, states=states)

    half = _panel(layer, 0, 1)
    assert (half['width'], half['x']) == (64, 128)
    assert _right(half) == 192

    contour = _compute_panel_contour(layer)
    assert contour == [(192, 0), (0, 0), (0, 384), (192, 384)]
    assert max(x for x, _ in contour) == _right(half) == 192
    assert max(x for x, _ in contour) != 2 * 128   # the old, wrong answer
    _assert_axis_aligned_loop(contour)
    _assert_matches_visible_bounds(layer, contour)


def test_mixed_half_row_does_not_collapse():
    """One half-height panel in an otherwise full row: the ROW keeps its full
    height (row height = max over the row), the half tile renders short inside
    its full-size slot, and the contour follows that real step.

    Expectations come from the panels _build_panels actually produced.
    """
    layer = _screen(3, 2, 128, 128, states={(2, 0): {'halfTile': 'height'}})

    short = _panel(layer, 2, 0)
    tall = _panel(layer, 2, 1)
    assert short['height'] == 64 and tall['height'] == 128   # row did NOT collapse
    assert short['y'] == tall['y'] == 256                    # same slot top
    assert _bottom(short) == 320 and _bottom(tall) == 384

    contour = _compute_panel_contour(layer)
    assert contour == [
        (_right(tall), _top(_panel(layer, 0, 0))),   # (256, 0)
        (_left(short), _top(_panel(layer, 0, 0))),   # (0, 0)
        (_left(short), _bottom(short)),              # (0, 320) short panel's real bottom
        (_right(short), _bottom(short)),             # (128, 320) step across
        (_right(short), _bottom(tall)),              # (128, 384) step down
        (_right(tall), _bottom(tall)),               # (256, 384)
    ]
    _assert_axis_aligned_loop(contour)
    _assert_matches_visible_bounds(layer, contour)


def test_half_height_top_row_anchored_to_bottom_of_slot():
    """A half tile anchored to the BOTTOM of its slot leaves the gap on the
    outer edge, so the contour must notch inward at the top."""
    layer = _screen(3, 2, 128, 128, states={(0, 0): {'halfTile': 'height'}})

    short = _panel(layer, 0, 0)
    full = _panel(layer, 0, 1)
    assert short['height'] == 64 and short['y'] == 64   # anchored to slot bottom
    assert full['y'] == 0

    bl = _panel(layer, 2, 0)
    br = _panel(layer, 2, 1)
    contour = _compute_panel_contour(layer)
    assert contour == [
        (_right(full), _top(full)),      # (256, 0)
        (_right(short), _top(full)),     # (128, 0)  top edge stops at the full panel
        (_right(short), _top(short)),    # (128, 64) down into the notch
        (_left(short), _top(short)),     # (0, 64)   across the notch floor
        (_left(bl), _bottom(bl)),        # (0, 384)
        (_right(br), _bottom(br)),       # (256, 384)
    ]
    _assert_axis_aligned_loop(contour)
    _assert_matches_visible_bounds(layer, contour)


# ── concavities from hidden panels (must keep working) ────────────────────

def test_hidden_corner_panel_makes_l_shape():
    """Hiding the bottom-right cabinet cuts an L: the contour steps around it
    instead of returning the bounding box."""
    layer = _screen(3, 4, 128, 128, states={(2, 3): {'hidden': True}})
    contour = _compute_panel_contour(layer)
    assert contour == [(512, 0), (0, 0), (0, 384), (384, 384), (384, 256), (512, 256)]
    _assert_axis_aligned_loop(contour)


def test_hidden_edge_panel_makes_notch():
    """A hidden panel in the middle of the right edge notches the contour."""
    layer = _screen(3, 4, 128, 128, states={(1, 3): {'hidden': True}})
    contour = _compute_panel_contour(layer)
    assert contour == [
        (512, 0), (0, 0), (0, 384), (512, 384),
        (512, 256), (384, 256), (384, 128), (512, 128),
    ]


def test_hidden_panels_with_half_row_together():
    """Half tiles and hidden panels combine: the L-step lands on the real
    halved height, not a cabinet lower."""
    states = {(2, c): {'halfTile': 'height'} for c in range(3)}
    states[(2, 2)] = {'halfTile': 'height', 'hidden': True}
    layer = _screen(3, 3, 128, 128, states=states)

    kept = _panel(layer, 2, 1)
    assert _bottom(kept) == 320
    contour = _compute_panel_contour(layer)
    assert contour == [
        (384, 0), (0, 0), (0, 320), (256, 320), (256, 256), (384, 256),
    ]
    _assert_axis_aligned_loop(contour)


# ── degenerate inputs ─────────────────────────────────────────────────────

def test_single_visible_panel():
    """One panel: a plain four-point rectangle in the documented winding."""
    layer = _screen(3, 3, 128, 128, states={
        (r, c): {'hidden': True} for r in range(3) for c in range(3)
        if (r, c) != (1, 1)
    })
    p = _panel(layer, 1, 1)
    contour = _compute_panel_contour(layer)
    assert contour == [
        (_right(p), _top(p)), (_left(p), _top(p)),
        (_left(p), _bottom(p)), (_right(p), _bottom(p)),
    ]
    assert contour == [(256, 128), (128, 128), (128, 256), (256, 256)]


def test_single_half_panel_uses_its_real_size():
    layer = _screen(1, 1, 128, 128, states={(0, 0): {'halfTile': 'width'}})
    p = _panel(layer, 0, 0)
    assert (p['width'], p['height']) == (64, 128)
    assert _compute_panel_contour(layer) == [(64, 0), (0, 0), (0, 128), (64, 128)]


def test_no_panels_returns_empty():
    assert _compute_panel_contour({'panels': []}) == []
    assert _compute_panel_contour({}) == []


def test_all_hidden_returns_empty():
    states = {(r, c): {'hidden': True} for r in range(3) for c in range(4)}
    layer = _screen(3, 4, 128, 128, states=states)
    assert layer['panels']            # panels exist, they are just all hidden
    assert _compute_panel_contour(layer) == []


def test_zero_size_panels_are_ignored():
    """A zero-size cabinet contributes no area and must not raise or emit a
    degenerate segment."""
    layer = _screen(2, 2, 0, 0)
    assert all(p['width'] == 0 and p['height'] == 0 for p in layer['panels'])
    assert _compute_panel_contour(layer) == []


def test_negative_size_panel_is_ignored():
    """A panel with a negative extent is skipped rather than inverting an edge."""
    layer = _screen(1, 2, 128, 128)
    layer['panels'][1]['width'] = -50
    p = layer['panels'][0]
    assert _compute_panel_contour(layer) == [
        (_right(p), _top(p)), (_left(p), _top(p)),
        (_left(p), _bottom(p)), (_right(p), _bottom(p)),
    ]


def test_missing_geometry_fields_do_not_raise():
    """Panels without x/y/width/height must not 500 the export."""
    layer = {'panels': [{'row': 0, 'col': 0, 'hidden': False}]}
    assert _compute_panel_contour(layer) == []


def test_offset_screen_with_half_row():
    """Offsets and half tiles together: everything shifts, nothing stretches."""
    states = {(1, c): {'halfTile': 'height'} for c in range(2)}
    layer = _screen(2, 2, 128, 128, off_x=500, off_y=300, states=states)
    bottom = _panel(layer, 1, 0)
    assert _bottom(bottom) == 300 + 128 + 64 == 492
    assert _compute_panel_contour(layer) == [(756, 300), (500, 300), (500, 492), (756, 492)]


def test_blank_panels_are_excluded_like_hidden_ones():
    """A blank cabinet is not lit surface, so the contour must not trace it.

    Every count that answers "where is the LED surface" filters on
    ``not blank and not hidden`` - cabinet totals (canvas.js:4640), weight,
    and power (app-power.js:1517). The contour used to consider only
    ``hidden``, so a blank corner was traced as if it were lit.
    """
    blank = _compute_panel_contour(_screen(3, 4, states={(2, 3): {'blank': True}}))
    hidden = _compute_panel_contour(_screen(3, 4, states={(2, 3): {'hidden': True}}))
    assert blank == hidden

    full = _compute_panel_contour(_screen(3, 4))
    assert blank != full
    assert len(blank) > len(full)
    _assert_axis_aligned_loop(blank)
