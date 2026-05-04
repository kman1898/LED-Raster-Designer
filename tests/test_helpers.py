"""Tests for internal helper functions."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app import _build_panels, _layer_bounds


def _make_layer(**overrides):
    """Create a minimal layer dict for testing helpers."""
    layer = {
        'columns': 3,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 80,
        'offset_x': 0,
        'offset_y': 0,
        # Legacy half flags, _build_panels migrates these to per-panel
        # halfTile values on first call and clears them. New code should
        # set halfTile per-panel via panel_states.
        'halfFirstColumn': False,
        'halfLastColumn': False,
        'halfFirstRow': False,
        'halfLastRow': False,
    }
    layer.update(overrides)
    return layer


def test_panel_width_normal():
    layer = _make_layer(cabinet_width=128)
    panels = _build_panels(layer)
    # Every panel is full-width when no half-tile state is set.
    for p in panels:
        assert p['width'] == 128


def test_panel_width_half_first_legacy_migrates():
    # Legacy halfFirstColumn flag is migrated into per-panel halfTile='width'.
    layer = _make_layer(cabinet_width=128, halfFirstColumn=True)
    panels = _build_panels(layer)
    first_col = [p for p in panels if p['col'] == 0]
    other_col = [p for p in panels if p['col'] == 1]
    for p in first_col:
        assert p['width'] == 64
        assert p['halfTile'] == 'width'
    for p in other_col:
        assert p['width'] == 128
    # The legacy flag should be cleared after migration.
    assert layer.get('halfFirstColumn') is False


def test_panel_width_half_last_legacy_migrates():
    # Legacy halfLastColumn flag also migrates correctly.
    layer = _make_layer(cabinet_width=128, halfLastColumn=True)
    panels = _build_panels(layer)
    last_col = [p for p in panels if p['col'] == layer['columns'] - 1]
    middle_col = [p for p in panels if p['col'] == 1]
    for p in last_col:
        assert p['width'] == 64
        assert p['halfTile'] == 'width'
    for p in middle_col:
        assert p['width'] == 128


def test_panel_height_half_first_legacy_migrates():
    # halfFirstRow → halfTile='height' on row 0 panels.
    layer = _make_layer(cabinet_height=100, halfFirstRow=True)
    panels = _build_panels(layer)
    row0 = [p for p in panels if p['row'] == 0]
    row1 = [p for p in panels if p['row'] == 1]
    for p in row0:
        assert p['height'] == 50
        assert p['halfTile'] == 'height'
    for p in row1:
        assert p['height'] == 100


def test_per_panel_half_tile_via_state():
    # New model: set halfTile per-panel in panel_states, keyed by (row, col).
    layer = _make_layer(columns=4, rows=3, cabinet_width=128, cabinet_height=128)
    states = {
        (0, 0): {'halfTile': 'height'},  # top-left corner: half-height
        (1, 0): {'halfTile': 'width'},   # left edge mid: half-width
    }
    panels = _build_panels(layer, panel_states=states)
    by_pos = {(p['row'], p['col']): p for p in panels}
    assert by_pos[(0, 0)]['halfTile'] == 'height'
    assert by_pos[(0, 0)]['height'] == 64
    assert by_pos[(0, 0)]['width'] == 128
    assert by_pos[(1, 0)]['halfTile'] == 'width'
    assert by_pos[(1, 0)]['width'] == 64
    assert by_pos[(1, 0)]['height'] == 128
    # Other panels stay full size.
    assert by_pos[(1, 1)]['halfTile'] == 'none'
    assert by_pos[(1, 1)]['width'] == 128
    assert by_pos[(1, 1)]['height'] == 128


def test_build_panels_count():
    layer = _make_layer(columns=4, rows=3)
    panels = _build_panels(layer)
    assert len(panels) == 12


def test_build_panels_positions():
    layer = _make_layer(columns=2, rows=2, cabinet_width=100, cabinet_height=80, offset_x=10, offset_y=20)
    panels = _build_panels(layer)
    by_pos = {(p['row'], p['col']): p for p in panels}
    # First panel (row 0, col 0)
    assert by_pos[(0, 0)]['x'] == 10
    assert by_pos[(0, 0)]['y'] == 20
    # Second panel (row 0, col 1)
    assert by_pos[(0, 1)]['x'] == 110
    assert by_pos[(0, 1)]['y'] == 20
    # Third panel (row 1, col 0)
    assert by_pos[(1, 0)]['x'] == 10
    assert by_pos[(1, 0)]['y'] == 100


def test_build_panels_preserves_state():
    # panel_states is keyed by (row, col) so state survives column/row
    # resizes (the previous id-keyed scheme scattered blanks across the wall
    # when columns changed).
    layer = _make_layer(columns=2, rows=1)
    states = {
        (0, 0): {'hidden': True, 'blank': False},
        (0, 1): {'hidden': False, 'blank': True},
    }
    panels = _build_panels(layer, panel_states=states)
    by_pos = {(p['row'], p['col']): p for p in panels}
    assert by_pos[(0, 0)]['hidden'] is True
    assert by_pos[(0, 1)]['blank'] is True


def test_build_panels_state_keyed_by_position():
    # Resizing columns shouldn't shuffle hidden/blank/halfTile state.
    # Build a 4-col layer with a hidden panel at (0, 2), then "resize" to
    # 6 cols by passing the same states dict, the hidden panel should
    # still be at (0, 2).
    layer = _make_layer(columns=4, rows=2)
    states = {(0, 2): {'hidden': True, 'blank': False, 'halfTile': 'none'}}
    panels = _build_panels(layer, panel_states=states)
    by_pos = {(p['row'], p['col']): p for p in panels}
    assert by_pos[(0, 2)]['hidden'] is True

    layer2 = _make_layer(columns=6, rows=2)
    panels2 = _build_panels(layer2, panel_states=states)
    by_pos2 = {(p['row'], p['col']): p for p in panels2}
    assert by_pos2[(0, 2)]['hidden'] is True
    # Newly-added cells (cols 4, 5) get default state.
    assert by_pos2[(0, 4)]['hidden'] is False
    assert by_pos2[(0, 5)]['hidden'] is False


def test_half_tile_anchors_to_neighbor():
    # Half-height panel at the top edge of a wall (no above neighbor) should
    # anchor to the bottom of its row slot so it visually connects to row 1.
    # When the whole row is half-height the slot collapses, so anchoring is a
    # no-op; we test the mixed case here.
    layer = _make_layer(columns=2, rows=2, cabinet_width=100, cabinet_height=80, offset_x=0, offset_y=0)
    states = {(0, 0): {'halfTile': 'height'}}  # only one panel in row 0 is half
    panels = _build_panels(layer, panel_states=states)
    by_pos = {(p['row'], p['col']): p for p in panels}
    half = by_pos[(0, 0)]
    full_neighbor = by_pos[(0, 1)]
    # Row 0 stays full-height because col 1 is a full panel; the half panel
    # renders in the bottom half of the slot, touching row 1 below.
    assert full_neighbor['height'] == 80
    assert half['height'] == 40
    # half.y + half.height == row 1 top edge (no gap between half and row 1)
    assert half['y'] + half['height'] == by_pos[(1, 0)]['y']


def test_layer_bounds_from_panels():
    layer = _make_layer()
    layer['panels'] = _build_panels(layer)
    bounds = _layer_bounds(layer)
    assert bounds['x'] == 0
    assert bounds['y'] == 0
    assert bounds['width'] == 300  # 3 * 100
    assert bounds['height'] == 160  # 2 * 80


def test_layer_bounds_with_offset():
    layer = _make_layer(offset_x=50, offset_y=30)
    layer['panels'] = _build_panels(layer)
    bounds = _layer_bounds(layer)
    assert bounds['x'] == 50
    assert bounds['y'] == 30


def test_layer_bounds_no_panels():
    layer = _make_layer(columns=4, rows=3, cabinet_width=100, cabinet_height=80)
    layer['panels'] = []
    bounds = _layer_bounds(layer)
    assert bounds['width'] == 400
    assert bounds['height'] == 240
