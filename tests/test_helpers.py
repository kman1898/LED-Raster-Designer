"""Tests for internal helper functions."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app import _build_panels, _panel_width, _panel_height, _layer_bounds


def _make_layer(**overrides):
    """Create a minimal layer dict for testing helpers."""
    layer = {
        'columns': 3,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 80,
        'offset_x': 0,
        'offset_y': 0,
        'halfFirstColumn': False,
        'halfLastColumn': False,
        'halfFirstRow': False,
        'halfLastRow': False,
    }
    layer.update(overrides)
    return layer


def test_panel_width_normal():
    layer = _make_layer(cabinet_width=128)
    assert _panel_width(layer, 0) == 128
    assert _panel_width(layer, 1) == 128


def test_panel_width_half_first():
    layer = _make_layer(cabinet_width=128, halfFirstColumn=True)
    assert _panel_width(layer, 0) == 64
    assert _panel_width(layer, 1) == 128


def test_panel_width_half_last():
    layer = _make_layer(cabinet_width=128, halfLastColumn=True)
    assert _panel_width(layer, 2) == 64  # last col (index 2 of 3)
    assert _panel_width(layer, 1) == 128


def test_panel_height_half_first():
    layer = _make_layer(cabinet_height=100, halfFirstRow=True)
    assert _panel_height(layer, 0) == 50
    assert _panel_height(layer, 1) == 100


def test_build_panels_count():
    layer = _make_layer(columns=4, rows=3)
    panels = _build_panels(layer)
    assert len(panels) == 12


def test_build_panels_positions():
    layer = _make_layer(columns=2, rows=2, cabinet_width=100, cabinet_height=80, offset_x=10, offset_y=20)
    panels = _build_panels(layer)
    # First panel
    assert panels[0]['x'] == 10
    assert panels[0]['y'] == 20
    # Second panel (col 1)
    assert panels[1]['x'] == 110
    assert panels[1]['y'] == 20
    # Third panel (row 1, col 0)
    assert panels[2]['x'] == 10
    assert panels[2]['y'] == 100


def test_build_panels_preserves_state():
    layer = _make_layer(columns=2, rows=1)
    states = {1: {'hidden': True, 'blank': False}, 2: {'hidden': False, 'blank': True}}
    panels = _build_panels(layer, panel_states=states)
    assert panels[0]['hidden'] is True
    assert panels[1]['blank'] is True


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
