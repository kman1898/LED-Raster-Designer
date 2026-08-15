#!/usr/bin/env python3
"""Turn a project into a NovaStar .scr.

Lives in src/ so the app can export through it when the SCR UI is rewired (the
in-app entry is currently parked); tools/scr_export.py is a thin command-line
front end onto the same code, so the button and the CLI can never disagree
about what a canvas means.

    python3 tools/scr_export.py --url http://localhost:8061 --out wall.scr
    python3 tools/scr_export.py --project saved.json --out wall.scr

The binary layer (src/scr_encoder.py) is not touched here - it already
re-encodes a real show file byte for byte. This is the layer ABOVE it: it turns
a project into the list of section dicts that build_multi_screen_scr() takes.

THE MODEL
---------
A NovaLCT "screen" - one section of the .scr - is a CANVAS in this app, NOT a
screen layer. One canvas is one section on one sending card, and the sending
card index is that canvas's position in project['canvases']. The screen LAYERS
on a canvas are the cabinets INSIDE that section, so a canvas carrying three
layers is ONE section holding all three layers' cabinets.

An earlier attempt mapped one section per LAYER. Two layers only ever collapsed
into one section there by coincidence - same screen number AND same sending
card - which is not a model. See docs/scr-app-integration-notes.md.

CONVENTIONS THAT CAME FROM MEASUREMENT, NOT ASSUMPTION
------------------------------------------------------
Both are recorded in tests/test_scr_roundtrip.py and are reproduced here rather
than re-derived:

* the encoder takes 1-BASED port numbers, though the file stores them 0-based;
* the encoder owns the row rotation. It looks up (col, (binary_row + 1) % rows),
  so the `row` handed to it is the APP row - 0 is the top of the section - and
  nothing here rotates anything.

Getting either wrong took a round trip from 0.6% to 7-8% differing bytes, so
they are not re-litigated in this file.

The port and chain maths is a port of calculatePortAssignments() in
src/static/js/app-export-io.js and the helpers it leans on in app-screen-info.js
and app-colors.js. It is deliberately a transcription: where the JS is odd, this
is odd the same way, because the two have to agree about which cabinet is on
which port. Anything that could NOT be carried across faithfully warns by name
instead of guessing quietly - run with the warnings visible before trusting a
file in NovaLCT.
"""

import argparse
import collections
import json
import os
import sys
import urllib.request

from scr_decoder import decode_scr  # noqa: E402
from scr_encoder import build_multi_screen_scr  # noqa: E402


# ── warnings ─────────────────────────────────────────────────────────────
#
# Every approximation this tool makes has to be able to say so. A .scr that is
# subtly wrong looks exactly like one that is right until a cabinet goes dark
# on site, so the rule here is that nothing is skipped silently.

class Warnings:
    """Collects what the run could not do faithfully, once per distinct issue."""

    def __init__(self):
        self.items = []
        self._seen = set()

    def warn(self, key, message):
        if key in self._seen:
            return
        self._seen.add(key)
        self.items.append(message)

    def __len__(self):
        return len(self.items)


# ── JS number coercion ───────────────────────────────────────────────────

def _num(value):
    """JS `Number(x) || 0` - anything not a usable number reads as 0.

    The JS leans on this everywhere it touches panel geometry, so a panel with
    a null width contributes 0 rather than raising. Reproduced so a project
    that survives the app also survives this tool.
    """
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if n != n else n


def _int(value, default=0):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


# ── capacity tables (app-core.js portCapacityTables) ─────────────────────
#
# Copied verbatim from the manufacturer figures in app-core.js. They are NOT
# derived from a formula there and are not derived from one here either - a
# processor/frame-rate pair the manufacturer does not publish has no answer,
# and 0 is how both sides say so.

PORT_CAPACITY_TABLES = {
    'novastar-armor': {
        8: {24: 1649306, 25: 1583333, 30: 1319444, 50: 791667, 60: 659722, 120: 329861},
        10: {24: 824653, 25: 791667, 30: 659722, 50: 395833, 60: 329861, 120: 164931},
        12: {24: 824653, 25: 791667, 30: 659722, 50: 395833, 60: 329861, 120: 164931},
    },
    'novastar-coex-1g': {
        8: {24: 1649306, 25: 1583333, 30: 1319444, 50: 791667, 60: 659722,
            120: 329861, 144: 274884, 240: 164931},
        10: {24: 1236979, 25: 1187500, 30: 989583, 50: 593750, 60: 494792,
             120: 247396, 144: 206163, 240: 123698},
        12: {24: 824653, 25: 791667, 30: 659722, 50: 395833, 60: 329861,
             120: 164931, 144: 137442, 240: 82465},
    },
    'novastar-5g': {
        8: {24: 7378000, 25: 7082800, 30: 5902400, 50: 3541440, 60: 2951200,
            120: 1475600, 144: 1229600, 240: 737800},
        10: {24: 5728280, 25: 5499149, 30: 4582624, 50: 2749574, 60: 2291312,
             120: 1145656, 144: 954713, 240: 572828},
        12: {24: 3689000, 25: 3541440, 30: 2951200, 50: 1770720, 60: 1475600,
             120: 737800, 144: 612374, 240: 368900},
    },
    'brompton': {
        8: {24: 1312500, 25: 1260000, 30: 1050000, 48: 656250, 50: 630000, 60: 525000,
            72: 437500, 100: 315000, 120: 262500, 144: 218750, 150: 210000, 180: 175000,
            192: 164063, 200: 157500, 240: 131250, 250: 126000},
        10: {24: 1050000, 25: 1008000, 30: 840000, 48: 525000, 50: 504000, 60: 420000,
             72: 350000, 100: 252000, 120: 210000, 144: 175000, 150: 168000, 180: 140000,
             192: 131250, 200: 126000, 240: 105000, 250: 100800},
        12: {24: 875000, 25: 840000, 30: 700000, 48: 437500, 50: 420000, 60: 350000,
             72: 291667, 100: 210000, 120: 175000, 144: 145833, 150: 140000, 180: 116667,
             192: 109375, 200: 105000, 240: 87500, 250: 84000},
    },
    'brompton-ull': {
        8: {24: 656250, 25: 630000, 30: 525000, 48: 328125, 50: 315000, 60: 262500,
            72: 218750, 100: 157500, 120: 131250, 144: 109375, 150: 105000, 180: 87500,
            192: 82031, 200: 78750, 240: 65625, 250: 63000},
        10: {24: 525000, 25: 504000, 30: 420000, 48: 262500, 50: 252000, 60: 210000,
             72: 175000, 100: 126000, 120: 105000, 144: 87500, 150: 84000, 180: 70000,
             192: 65625, 200: 63000, 240: 52500, 250: 50400},
        12: {24: 437500, 25: 420000, 30: 350000, 48: 218750, 50: 210000, 60: 175000,
             72: 145833, 100: 105000, 120: 87500, 144: 72917, 150: 70000, 180: 58333,
             192: 54688, 200: 52500, 240: 43750, 250: 42000},
    },
    'megapixel-1g': {
        10: {24: 1237000, 25: 1187000, 30: 985000, 48: 608000, 50: 583000, 60: 482000,
             120: 230000, 144: 188000, 180: 146000, 200: 129000, 240: 104000},
        12: {24: 1031000, 25: 989000, 30: 821000, 48: 506000, 50: 485000, 60: 401000,
             120: 192000, 144: 157000, 180: 122000, 200: 108000, 240: 87000},
    },
    'megapixel-2.5g': {
        10: {24: 3094000, 25: 2968000, 30: 2464000, 48: 1520000, 50: 1457000, 60: 1205000,
             120: 576000, 144: 471000, 180: 366000, 200: 324000, 240: 261000},
        12: {24: 2578000, 25: 2473000, 30: 2053000, 48: 1267000, 50: 1214000, 60: 1004000,
             120: 480000, 144: 393000, 180: 305000, 200: 270000, 240: 218000},
    },
}

# app-core.js lowLatencyProfiles, reduced to the two fields the maths reads.
# The notes/rules/cards text is UI copy and has no business here.
LOW_LATENCY_PROFILES = {
    'novastar-armor': {'supported': True, 'capacity': {'kind': 'novastar-ll', 'yDerate': True}},
    'novastar-coex-1g': {'supported': True, 'capacity': {'kind': 'novastar-ll', 'yDerate': True}},
    'novastar-5g': {'supported': True, 'capacity': {'kind': 'novastar-ll', 'yDerate': True}},
    'brompton': {'supported': True, 'capacity': {'kind': 'factor', 'factor': 0.5}},
}


def lookup_port_capacity(bit_depth, frame_rate, processor_type):
    """Raw manufacturer-table lookup, before any Low Latency behaviour."""
    processor_type = processor_type or 'novastar-armor'
    table = PORT_CAPACITY_TABLES.get(processor_type)
    if not table:
        return 0

    use_bit_depth = bit_depth
    if bit_depth not in table:
        # Closest available depth, matching the JS reduce (which keeps the
        # first entry on a tie, so the iteration order of the table matters).
        use_bit_depth = None
        for bd in table:
            if use_bit_depth is None:
                use_bit_depth = bd
            elif abs(bd - _num(bit_depth)) < abs(use_bit_depth - _num(bit_depth)):
                use_bit_depth = bd

    fps_table = table.get(use_bit_depth)
    if not fps_table:
        return 0

    exact_fps = _int(round(_num(frame_rate)))
    if fps_table.get(exact_fps):
        return fps_table[exact_fps]

    fps_list = sorted(fps_table)
    rate = _num(frame_rate)

    lower = fps_list[0]
    upper = fps_list[-1]
    for i in range(len(fps_list) - 1):
        if fps_list[i] <= rate <= fps_list[i + 1]:
            lower = fps_list[i]
            upper = fps_list[i + 1]
            break

    # Below the table: clamp UP to the lowest published row - the conservative
    # direction, more ports than needed and never fewer.
    if rate <= fps_list[0]:
        return fps_table[fps_list[0]]
    # Above the table: no capacity. Clamping to the last row answered a 240 Hz
    # question with a 120 Hz figure - double the real capacity, half the ports.
    if rate > fps_list[-1]:
        return 0

    ratio = (rate - lower) / (upper - lower)
    return int(fps_table[lower] + (fps_table[upper] - fps_table[lower]) * ratio)


def get_low_latency_profile(processor_type):
    return LOW_LATENCY_PROFILES.get(processor_type or 'novastar-armor')


def apply_low_latency_capacity(capacity, processor_type, low_latency):
    """'factor' halves and floors; 'novastar-ll' is geometric and comes back
    unchanged - its (1 - Y/H) derate needs each port's position and is applied
    in calculate_port_assignments instead."""
    if not low_latency or not capacity > 0:
        return capacity
    profile = get_low_latency_profile(processor_type)
    if not profile or not profile.get('supported'):
        return capacity
    cap = profile.get('capacity') or {}
    if cap.get('kind') == 'factor':
        return int(capacity * cap['factor'])
    return capacity


def calculate_port_capacity(bit_depth, frame_rate, processor_type, low_latency=False):
    capacity = lookup_port_capacity(bit_depth, frame_rate, processor_type)
    return apply_low_latency_capacity(capacity, processor_type, low_latency)


def get_low_latency_geometry(layer):
    """The geometric Low Latency rules for this layer, or None."""
    if not layer or not layer.get('lowLatency'):
        return None
    if (layer.get('type') or 'screen') != 'screen':
        return None
    profile = get_low_latency_profile(layer.get('processorType') or 'novastar-armor')
    if not profile or not profile.get('supported'):
        return None
    cap = profile.get('capacity') or {}
    return cap if cap.get('kind') == 'novastar-ll' else None


def low_latency_port_capacity(total, min_y, canvas_height):
    """Capacity of one Low Latency port whose topmost cabinet sits at min_y.
    Y = 0 - a top-aligned port - costs nothing. An unknown height derates
    nothing rather than guessing an H."""
    if not total > 0:
        return 0
    if not canvas_height > 0:
        return total
    factor = min(1.0, max(0.0, 1 - (_num(min_y) / canvas_height)))
    return int(factor * total)


def novastar_min_load_width(processor_type):
    """NovaStar 5G's minimum Ethernet-port load width, 0 everywhere else -
    which is "the rule does not exist there", not "the threshold is zero".
    Published under the 5G table only; do not widen it without a source."""
    return 128 if processor_type == 'novastar-5g' else 0


def min_load_width_port_capacity(capacity, processor_type, width, height):
    min_width = novastar_min_load_width(processor_type)
    if not min_width > 0 or not capacity > 0:
        return capacity
    w = _num(width)
    h = _num(height)
    if not w > 0 or not h > 0 or w >= min_width:
        return capacity
    return max(0, capacity - ((min_width - w) * h))


def uses_rectangle_constraint(processor_type):
    return processor_type == 'novastar-armor'


def full_panel_pixels(layer):
    return _num(layer.get('cabinet_width')) * _num(layer.get('cabinet_height'))


def panel_pixel_area(panel):
    if not panel:
        return 0
    return _num(panel.get('width')) * _num(panel.get('height'))


# ── traversal (app-screen-info.js) ───────────────────────────────────────

def get_ordered_panels_by_pattern(layer, pattern='tl-h', include_hidden=False):
    """The cabinets of a layer in its flow order.

    Note what a 'custom' pattern does here: it has no '-h'/'-v' suffix, so it
    falls through to the tl default with a vertical-first reading of False.
    That is what the JS does, and the export path only reaches this with a
    custom pattern when the layer has no drawn paths to walk instead.
    """
    panels = layer.get('panels')
    if not layer or not isinstance(panels, list) or not panels:
        return []
    cols = _int(layer.get('columns'))
    rows = _int(layer.get('rows'))
    if cols <= 0 or rows <= 0:
        return []

    panel_map = {}
    for panel in panels:
        panel_map[(_int(panel.get('row')), _int(panel.get('col')))] = panel

    parts = str(pattern).split('-')
    start_corner = parts[0]
    direction = parts[1] if len(parts) > 1 else None

    start_row = 0
    start_col = 0
    row_dir = 1
    col_dir = 1
    if start_corner == 'tr':
        start_col = cols - 1
        col_dir = -1
    elif start_corner == 'bl':
        start_row = rows - 1
        row_dir = -1
    elif start_corner == 'br':
        start_row = rows - 1
        start_col = cols - 1
        row_dir = -1
        col_dir = -1

    ordered = []

    def take(r, c):
        panel = panel_map.get((r, c))
        if panel is not None and (include_hidden or not panel.get('hidden')):
            ordered.append(panel)

    if direction == 'v':
        c = start_col
        while 0 <= c < cols:
            reverse = abs(c - start_col) % 2 == 1
            if reverse:
                r = start_row + (rows - 1) * row_dir
                while 0 <= r < rows:
                    take(r, c)
                    r -= row_dir
            else:
                r = start_row
                while 0 <= r < rows:
                    take(r, c)
                    r += row_dir
            c += col_dir
    else:
        r = start_row
        while 0 <= r < rows:
            reverse = abs(r - start_row) % 2 == 1
            if reverse:
                c = start_col + (cols - 1) * col_dir
                while 0 <= c < cols:
                    take(r, c)
                    c -= col_dir
            else:
                c = start_col
                while 0 <= c < cols:
                    take(r, c)
                    c += col_dir
            r += row_dir

    return ordered


def get_organized_panels_for_units(layer, pattern, is_horizontal_first,
                                   ordered_unit_indices, include_hidden=False):
    """The cabinets of a port, in cable order: each row/column serpentines
    against the one before it, so the run does not fly back across the wall."""
    panels = layer.get('panels')
    if not isinstance(panels, list) or not isinstance(ordered_unit_indices, list):
        return []
    starts_top = str(pattern).startswith('t')
    starts_left = 'l-' in str(pattern)

    panel_map = {}
    for panel in panels:
        panel_map[(_int(panel.get('row')), _int(panel.get('col')))] = panel

    cols = _int(layer.get('columns'))
    rows = _int(layer.get('rows'))
    ordered = []
    for unit_pos, unit_idx in enumerate(ordered_unit_indices):
        if is_horizontal_first:
            left_to_right = (unit_pos % 2 == 0) if starts_left else (unit_pos % 2 != 0)
            col_range = range(cols) if left_to_right else range(cols - 1, -1, -1)
            for col in col_range:
                panel = panel_map.get((unit_idx, col))
                if panel is None:
                    continue
                if include_hidden or not panel.get('hidden'):
                    ordered.append(panel)
        else:
            top_to_bottom = (unit_pos % 2 == 0) if starts_top else (unit_pos % 2 != 0)
            row_range = range(rows) if top_to_bottom else range(rows - 1, -1, -1)
            for row in row_range:
                panel = panel_map.get((row, unit_idx))
                if panel is None:
                    continue
                if include_hidden or not panel.get('hidden'):
                    ordered.append(panel)
    return ordered


# ── rectangle bookkeeping ────────────────────────────────────────────────

def _panel_rect(panel):
    x1 = _num(panel.get('x'))
    y1 = _num(panel.get('y'))
    return {'minX': x1, 'minY': y1,
            'maxX': x1 + _num(panel.get('width')),
            'maxY': y1 + _num(panel.get('height')), 'count': 1}


def _union_rect(rect, panel):
    if rect['count'] == 0:
        return _panel_rect(panel)
    r = _panel_rect(panel)
    return {'minX': min(rect['minX'], r['minX']), 'minY': min(rect['minY'], r['minY']),
            'maxX': max(rect['maxX'], r['maxX']), 'maxY': max(rect['maxY'], r['maxY']),
            'count': rect['count'] + 1}


def _rect_area(rect):
    if not rect or rect['count'] == 0:
        return 0
    return (rect['maxX'] - rect['minX']) * (rect['maxY'] - rect['minY'])


def _empty_rect():
    return {'minX': 0, 'minY': 0, 'maxX': 0, 'maxY': 0, 'count': 0}


# ── the port walk (app-export-io.js calculatePortAssignments) ────────────

def calculate_port_assignments(layer, canvas_height=0, warnings=None):
    """Cabinets to ports, as the app computes them.

    Returns a list of {'panel', 'port', 'is_port_start', 'pixel_index'} with
    1-based ports, or [] when the layer cannot be mapped at all - an
    unpublished frame rate, or one cabinet too big for an empty port. Both are
    hard errors in the app too; it draws ERROR rather than a plausible map, and
    this returns nothing rather than writing one into a show file.
    """
    if not layer or not isinstance(layer.get('panels'), list):
        return []

    bit_depth = _int(layer.get('bitDepth') or 8, 8)
    frame_rate = _num(layer.get('frameRate') or 60)
    processor_type = layer.get('processorType') or 'novastar-armor'
    mapping_mode = layer.get('portMappingMode') or 'organized'
    port_capacity = calculate_port_capacity(
        bit_depth, frame_rate, processor_type, bool(layer.get('lowLatency')))
    pattern = layer.get('flowPattern') or 'tl-h'
    rect_constraint = uses_rectangle_constraint(processor_type)
    is_organized = mapping_mode == 'organized'
    is_horizontal_first = '-h' in str(pattern)
    starts_top = str(pattern).startswith('t')
    starts_left = 'l-' in str(pattern)
    panel_pixels = full_panel_pixels(layer)
    ll_geometry = get_low_latency_geometry(layer)
    min_load_width = novastar_min_load_width(processor_type)

    if port_capacity <= 0 or panel_pixels <= 0:
        if warnings is not None and port_capacity <= 0:
            warnings.warn(
                'no-capacity-%s' % layer.get('id'),
                'layer %s ("%s"): %s publishes no port capacity at %s-bit / %g Hz, '
                'so NO ports could be assigned and every cabinet is written as a '
                'placeholder. Pick a published frame rate.'
                % (layer.get('id'), layer.get('name'), processor_type, bit_depth, frame_rate))
        return []

    ordered_for_capacity = get_ordered_panels_by_pattern(layer, pattern, rect_constraint)
    if not ordered_for_capacity:
        return []

    ports = []
    capacity_error = [None]

    def capacity_for_rect(base, rect):
        if min_load_width > 0 and rect and rect['count'] > 0:
            return min_load_width_port_capacity(
                base, processor_type, rect['maxX'] - rect['minX'], rect['maxY'] - rect['minY'])
        return base

    def raise_capacity_error(unit_type, unit_count):
        capacity_error[0] = {'unitType': unit_type, 'unitCount': unit_count}

    if ll_geometry:
        # Low Latency: no port-width cap (NovaStar removed the 512 px figure
        # their older manuals print), but ports load as vertical runs from the
        # top of the canvas and a port whose topmost cabinet sits at Y keeps
        # only (1 - Y/H). The traversal stays the USER'S flow pattern.
        height = canvas_height if ll_geometry.get('yDerate') else 0
        if ll_geometry.get('yDerate') and not height > 0 and warnings is not None:
            warnings.warn(
                'll-no-height-%s' % layer.get('id'),
                'layer %s ("%s"): Low Latency is on but its canvas has no raster '
                'height, so the (1 - Y/H) derate was NOT applied. Port count may be '
                'optimistic.' % (layer.get('id'), layer.get('name')))

        def capacity_at_y(min_y):
            if ll_geometry.get('yDerate'):
                return low_latency_port_capacity(port_capacity, min_y, height)
            return port_capacity

        def port_limit(min_y, bounds):
            # Order of operations is a decision: the table value, then the
            # (1 - Y/H) derate, THEN the 5G narrow-port penalty off what is
            # left. The other way round would scale the penalty by (1 - Y/H).
            return capacity_for_rect(capacity_at_y(min_y), bounds)

        ll_panels = [p for p in get_ordered_panels_by_pattern(layer, pattern, False)
                     if panel_pixel_area(p) > 0]
        if not ll_panels:
            return []

        current = None
        for panel in ll_panels:
            if capacity_error[0]:
                break
            area = panel_pixel_area(panel)
            y = _num(panel.get('y'))
            solo_rect = _panel_rect(panel) if rect_constraint else None
            solo_load = _rect_area(solo_rect) if rect_constraint else area
            solo_bounds = _panel_rect(panel) if min_load_width > 0 else None
            if current:
                # Adding a cabinet can only pull the port's top edge UP, so
                # re-derate against the candidate Y.
                cand_min_y = min(current['minY'], y)
                cand_rect = _union_rect(current['rect'], panel) if rect_constraint else None
                cand_load = (_rect_area(cand_rect) if rect_constraint
                             else current['load'] + area)
                cand_bounds = (_union_rect(current['bounds'], panel)
                               if min_load_width > 0 else None)
                if cand_load <= port_limit(cand_min_y, cand_bounds):
                    current['panels'].append(panel)
                    current['load'] = cand_load
                    current['minY'] = cand_min_y
                    current['rect'] = cand_rect
                    current['bounds'] = cand_bounds
                    continue
                ports.append(current)
                current = None
            # Only now, opening a fresh port, is a lone cabinet judged at its
            # OWN Y. Testing this first would fail a cabinet low on the canvas
            # that fits perfectly well on a port opened higher up.
            if solo_load > port_limit(y, solo_bounds):
                raise_capacity_error('panel', 1)
                break
            current = {'panels': [panel], 'load': solo_load, 'minY': y,
                       'rect': solo_rect, 'bounds': solo_bounds}
        if current and not capacity_error[0]:
            ports.append(current)
        if capacity_error[0]:
            ports = []

    elif is_organized:
        if is_horizontal_first:
            unit_indices = [i if starts_top else (_int(layer.get('rows')) - 1 - i)
                            for i in range(_int(layer.get('rows')))]
        else:
            unit_indices = [i if starts_left else (_int(layer.get('columns')) - 1 - i)
                            for i in range(_int(layer.get('columns')))]

        def unit_panels(idx):
            key = 'row' if is_horizontal_first else 'col'
            return [p for p in ordered_for_capacity if _int(p.get(key)) == idx]

        def bounding_rect_load(unit_idx_list):
            if not rect_constraint:
                # Non-rectangle processors: sum actual pixel areas.
                return sum(sum(panel_pixel_area(p) for p in unit_panels(idx))
                           for idx in unit_idx_list)
            # Rectangle constraint (Armor / 1G): the processor reserves the
            # pixel rectangle enclosing every visible cabinet in the port, so
            # half-tiles contribute their reduced footprint, not a whole cell.
            rect = _empty_rect()
            for idx in unit_idx_list:
                for p in unit_panels(idx):
                    if not p.get('hidden'):
                        rect = _union_rect(rect, p)
            return _rect_area(rect)

        def capacity_for_units(unit_idx_list):
            if not min_load_width > 0:
                return port_capacity
            bounds = _empty_rect()
            for idx in unit_idx_list:
                for p in unit_panels(idx):
                    if not p.get('hidden'):
                        bounds = _union_rect(bounds, p)
            return capacity_for_rect(port_capacity, bounds)

        current = {'unitIndices': [], 'load': 0}
        for unit_idx in unit_indices:
            all_in_unit = unit_panels(unit_idx)
            if not all_in_unit:
                continue
            visible = [p for p in all_in_unit if not p.get('hidden')]
            if not visible:
                continue

            if rect_constraint:
                rect = _empty_rect()
                for p in visible:
                    rect = _union_rect(rect, p)
                single_unit_load = _rect_area(rect)
            else:
                single_unit_load = sum(panel_pixel_area(p) for p in all_in_unit)

            # Judged against the capacity THIS unit has: on 5G a single narrow
            # column is penalised in its own right.
            if single_unit_load > capacity_for_units([unit_idx]):
                raise_capacity_error('row' if is_horizontal_first else 'column',
                                     _int(layer.get('columns')) if is_horizontal_first
                                     else _int(layer.get('rows')))
                break

            candidate = current['unitIndices'] + [unit_idx]
            candidate_load = bounding_rect_load(candidate)
            if current['unitIndices'] and candidate_load > capacity_for_units(candidate):
                current['load'] = bounding_rect_load(current['unitIndices'])
                ports.append(current)
                current = {'unitIndices': [unit_idx], 'load': single_unit_load}
            else:
                current['unitIndices'].append(unit_idx)
                current['load'] = candidate_load

        if capacity_error[0]:
            ports = []
        elif current['load'] > 0 or current['unitIndices']:
            ports.append(current)

    elif rect_constraint:
        # Max Capacity on a rectangle-constraint processor. The load is the
        # rectangle the processor reserves around the port's visible cabinets,
        # grown one cabinet at a time; a plain sum would under-count it and
        # emit a map that over-fills the port.
        current = {'panels': [], 'load': 0}
        current_rect = _empty_rect()
        for panel in ordered_for_capacity:
            if capacity_error[0]:
                break
            # Hidden cabinets sit physically inside the reserved rectangle, so
            # they are skipped outright rather than allowed to grow it: one
            # falling inside the visible rect is already paid for.
            if panel.get('hidden'):
                continue
            if panel_pixel_area(panel) <= 0:
                continue
            solo_load = _rect_area(_panel_rect(panel))
            if solo_load > port_capacity:
                raise_capacity_error('panel', 1)
                break
            candidate_rect = _union_rect(current_rect, panel)
            candidate_load = _rect_area(candidate_rect)
            if current['panels'] and candidate_load > port_capacity:
                current['load'] = _rect_area(current_rect)
                ports.append(current)
                current_rect = _panel_rect(panel)
                current = {'panels': [panel], 'load': solo_load}
            else:
                current['panels'].append(panel)
                current_rect = candidate_rect
                current['load'] = candidate_load
        if capacity_error[0]:
            ports = []
        elif current['panels']:
            ports.append(current)

    else:
        current = {'panels': [], 'load': 0}
        current_bounds = _empty_rect() if min_load_width > 0 else None
        for panel in ordered_for_capacity:
            if capacity_error[0]:
                break
            panel_load = panel_pixel_area(panel)
            if panel_load <= 0:
                continue
            candidate_bounds = _union_rect(current_bounds, panel) if current_bounds else None
            if (current['load'] > 0
                    and current['load'] + panel_load > capacity_for_rect(port_capacity,
                                                                         candidate_bounds)):
                ports.append(current)
                current = {'panels': [], 'load': 0}
                current_bounds = _empty_rect() if min_load_width > 0 else None
            if (min_load_width > 0 and current['load'] == 0
                    and panel_load > capacity_for_rect(port_capacity, _panel_rect(panel))):
                raise_capacity_error('panel', 1)
                break
            if not panel.get('hidden'):
                current['panels'].append(panel)
            if current_bounds is not None:
                current_bounds = _union_rect(current_bounds, panel)
            current['load'] += panel_load
        if capacity_error[0]:
            ports = []
        elif current['load'] > 0 or current['panels']:
            ports.append(current)

    if capacity_error[0]:
        if warnings is not None:
            err = capacity_error[0]
            warnings.warn(
                'capacity-error-%s' % layer.get('id'),
                'layer %s ("%s"): one %s does not fit on a port at %s-bit / %g Hz, '
                'which the app reports as ERROR rather than a map. NO ports were '
                'assigned for this layer and its cabinets are written as '
                'placeholders.' % (layer.get('id'), layer.get('name'),
                                   err['unitType'], bit_depth, frame_rate))
        return []

    assignments = []
    for idx, port in enumerate(ports):
        if is_organized and not ll_geometry:
            port_panels = get_organized_panels_for_units(
                layer, pattern, is_horizontal_first, port.get('unitIndices') or [], False)
        else:
            port_panels = port.get('panels') or []
        pixel_index = 0
        for panel_idx, panel in enumerate(port_panels):
            assignments.append({'panel': panel, 'port': idx + 1,
                                'is_port_start': panel_idx == 0,
                                'pixel_index': pixel_index})
            pixel_index += panel_pixel_area(panel)
    return assignments


def custom_port_assignments(layer, warnings=None):
    """Cabinets to ports from the user's DRAWN cables.

    customPortPaths is {"<port>": [{col, row}, ...]} - the order the cable was
    drawn IS the chain order, so nothing is re-sorted here. Ports are walked in
    ascending numeric order so port 10 lands after port 9 rather than after
    port 1, which a plain string sort would do.

    KNOWN GAP, not fixed here: a step may carry `layerId` naming a group PEER
    (v0.11.0 cross-member cables). The panel map below is built from this
    layer's own panels and the step's layerId is ignored, so a crossing step
    lands on the OWNER's cabinet at that row and column - a different cabinet,
    or none. Cross-member routing in the .scr is one job, and it is not this
    one; see crossing_groups() for the automatic half of the same gap.
    """
    paths = layer.get('customPortPaths') or {}
    if not isinstance(paths, dict) or not paths:
        return []

    panel_map = {}
    for panel in layer.get('panels') or []:
        panel_map[(_int(panel.get('row')), _int(panel.get('col')))] = panel

    def port_key(k):
        try:
            return (0, int(k))
        except (TypeError, ValueError):
            # A non-numeric key cannot be ordered against the numbers; it goes
            # last and says so rather than being dropped.
            if warnings is not None:
                warnings.warn('custom-port-key-%s-%s' % (layer.get('id'), k),
                              'layer %s ("%s"): custom cable port key %r is not a '
                              'number; it was ordered last.'
                              % (layer.get('id'), layer.get('name'), k))
            return (1, 0)

    assignments = []
    pixel_step = full_panel_pixels(layer)
    for port_no, key in enumerate(sorted(paths, key=port_key), start=1):
        path = paths[key] or []
        pixel_index = 0
        placed = 0
        for idx, step in enumerate(path):
            panel = panel_map.get((_int(step.get('row')), _int(step.get('col'))))
            if panel is None or panel.get('hidden'):
                continue
            assignments.append({'panel': panel, 'port': port_no,
                                'is_port_start': idx == 0,
                                'pixel_index': pixel_index})
            pixel_index += pixel_step
            placed += 1
        if not placed and warnings is not None:
            warnings.warn('custom-empty-%s-%s' % (layer.get('id'), key),
                          'layer %s ("%s"): drawn cable for port %s reaches no visible '
                          'cabinet; that port is empty in the .scr.'
                          % (layer.get('id'), layer.get('name'), key))
    return assignments


def assignments_for_layer(layer, canvas_height=0, warnings=None):
    """The layer's port map, from its drawn cables when it has them."""
    if (layer.get('flowPattern') == 'custom') and (layer.get('customPortPaths') or {}):
        return custom_port_assignments(layer, warnings)
    if layer.get('flowPattern') == 'custom' and warnings is not None:
        warnings.warn(
            'custom-no-paths-%s' % layer.get('id'),
            'layer %s ("%s"): flow pattern is Custom but no cables are drawn, so the '
            'default top-left traversal was used instead.'
            % (layer.get('id'), layer.get('name')))
    return calculate_port_assignments(layer, canvas_height, warnings)


# ── project -> sections ──────────────────────────────────────────────────

def _is_placeholder(panel):
    """A cabinet that carries no data. Hidden and blank are both drawn as a
    gap in the wall, and the .scr writes both as NovaStar's placeholder
    (sender 0xFF, port 1, chain 1) rather than routing a port to nothing."""
    return bool(panel.get('hidden')) or bool(panel.get('blank'))


def _canvas_offsets(layer):
    """How much to add to a panel's x/y to reach canvas coordinates.

    The server builds panels with the layer offset ALREADY in them - a layer at
    offset_x 2580 has its first column at x 2580 - and the app's own maths
    relies on that. A project written by hand may not, so the two are told
    apart by whether the leftmost cabinet already sits at the offset. They only
    coincide when the offset is 0, where the answer is the same either way.
    """
    panels = layer.get('panels') or []
    if not panels:
        return 0.0, 0.0
    off_x = _num(layer.get('offset_x'))
    off_y = _num(layer.get('offset_y'))
    min_x = min(_num(p.get('x')) for p in panels)
    min_y = min(_num(p.get('y')) for p in panels)
    dx = 0.0 if abs(min_x - off_x) < 0.5 else off_x
    dy = 0.0 if abs(min_y - off_y) < 0.5 else off_y
    return dx, dy


def build_canvas_section(project, canvas, canvas_index, layers, warnings):
    """One canvas -> one section dict for build_multi_screen_scr.

    The section's grid is derived from where the cabinets actually ARE. Layers
    on the same canvas sit at different offsets and can mix cabinet sizes, so
    the columns are the distinct cabinet left edges across the whole canvas and
    the rows are the distinct top edges. A cabinet's grid index is the position
    of its own edge in those lists.
    """
    cabinets = []
    port_base = 0
    canvas_height = _num(canvas.get('raster_height'))

    for layer in layers:
        dx, dy = _canvas_offsets(layer)
        assignments = assignments_for_layer(layer, canvas_height, warnings)

        # Chain order is a per-port counter in path order, starting at 0 -
        # the same convention the round trip reads back out of a real file.
        chain_counters = collections.Counter()
        routed = {}
        max_port = 0
        for a in assignments:
            panel = a['panel']
            if _is_placeholder(panel):
                # The JS traversal only knows about `hidden`, so a cabinet
                # marked blank can still come back with a port. It carries no
                # data, so the port slot is given back rather than written.
                if panel.get('blank') and not panel.get('hidden'):
                    warnings.warn(
                        'blank-routed-%s' % layer.get('id'),
                        'layer %s ("%s"): a blank cabinet was assigned a port by the '
                        'traversal; it is written as a placeholder instead.'
                        % (layer.get('id'), layer.get('name')))
                continue
            key = (_int(panel.get('col')), _int(panel.get('row')))
            if key in routed:
                continue
            port = port_base + a['port']
            routed[key] = (port, chain_counters[port])
            chain_counters[port] += 1
            max_port = max(max_port, a['port'])

        for panel in layer.get('panels') or []:
            key = (_int(panel.get('col')), _int(panel.get('row')))
            port, chain = routed.get(key, (0, 0))
            cabinets.append({
                'x': _num(panel.get('x')) + dx,
                'y': _num(panel.get('y')) + dy,
                'w': _num(panel.get('width')),
                'h': _num(panel.get('height')),
                'port_num': port,
                'chain_order': chain,
                'hidden': _is_placeholder(panel) or port == 0,
                'layer_id': layer.get('id'),
                'layer_name': layer.get('name'),
            })

        if max_port:
            # Ports are numbered per layer in the app, all starting at 1. A
            # canvas is one sending card, so a second layer's port 1 would
            # collide with the first layer's; later layers are shifted up
            # instead. Which run lands on which physical port is then a
            # decision this tool made, not one the user drew.
            if port_base:
                warnings.warn(
                    'port-offset-%s' % layer.get('id'),
                    'layer %s ("%s") shares canvas "%s" with an earlier layer, so its '
                    'ports were renumbered %d-%d to avoid colliding on the sending '
                    'card. Check that against the real cabling.'
                    % (layer.get('id'), layer.get('name'), canvas.get('name'),
                       port_base + 1, port_base + max_port))
            port_base += max_port

    if not cabinets:
        return None

    xs = sorted({round(c['x'], 3) for c in cabinets})
    ys = sorted({round(c['y'], 3) for c in cabinets})
    col_of = {x: i for i, x in enumerate(xs)}
    row_of = {y: i for i, y in enumerate(ys)}
    cols = len(xs)
    rows = len(ys)

    widths = collections.Counter(int(c['w']) for c in cabinets if c['w'] > 0)
    heights = collections.Counter(int(c['h']) for c in cabinets if c['h'] > 0)
    pw = widths.most_common(1)[0][0] if widths else 0
    ph = heights.most_common(1)[0][0] if heights else 0

    if len(widths) > 1 or len(heights) > 1:
        warnings.warn(
            'mixed-sizes-%s' % canvas.get('id'),
            'canvas "%s" mixes cabinet sizes (%s wide, %s high). Each cabinet keeps '
            'its own geometry, but the section grid is one cell per distinct edge, so '
            'it has cells no cabinet sits in.'
            % (canvas.get('name'), sorted(widths), sorted(heights)))

    # Every cell in the bounding grid is written - the encoder walks cols*rows
    # and a cell it finds nothing for would be emitted as a REAL cabinet on
    # port 1. So the holes are filled explicitly with placeholders.
    grid = {}
    for cab in cabinets:
        key = (col_of[round(cab['x'], 3)], row_of[round(cab['y'], 3)])
        if key in grid:
            warnings.warn(
                'overlap-%s' % canvas.get('id'),
                'canvas "%s": two cabinets share grid cell %s (layers %s and %s). The '
                'first one wins; the other is not in the .scr.'
                % (canvas.get('name'), key, grid[key]['layer_name'], cab['layer_name']))
            continue
        grid[key] = cab

    # The format reserves the last cell of the binary's last row - binary
    # (cols-1, rows-1), which the encoder's rotation makes the app's top row,
    # last column - for the section terminator. NovaStar makes room for it by
    # sliding that one row a single cell LEFT: the record at binary column c
    # carries the routing of the cabinet the app draws at column c+1, and the
    # cabinet in app column 0 is pushed off the grid entirely. Every other row
    # is untouched. Verified against all 16 sections of the reference corpus:
    # in each one exactly one port is missing exactly one link of its chain,
    # and it is always the top-left cabinet's.
    #
    # Only the ROUTING slides. Geometry stays with the cell it is drawn in -
    # each record keeps the x/y/w/h of its own grid position - which is what
    # the reference files show and what keeps a mixed-size wall in one piece.
    def routing_source(col, row):
        return grid.get((col + 1, row)) if row == 0 else grid.get((col, row))

    panels = []
    for col in range(cols):
        for row in range(rows):
            cab = grid.get((col, row))
            route = routing_source(col, row)
            # `row` here is the app row - 0 is the top of the wall - and the
            # encoder lands it at binary row (row - 1) % rows. The Y written is
            # that BINARY row's line, not the cabinet's own, because that is
            # what NovaStar writes: across the reference corpus every record
            # sits on the uniform grid y = screen_y + binary_row * height.
            #
            # The two only disagree on the wrapped top row, and the corpus
            # settles which one carries the wall's shape. Read by row index in
            # NovaLCT's order (binary row N-1 first, then 0..N-2) the reference
            # SR section comes out 10, 11, 20, 24, 35 ... 49 cabinets per row -
            # the app's wall exactly. Read by its Y values it comes out as a
            # wide wall with a stray 10-cabinet strip along the bottom, which is
            # not a wall anyone built. So the index carries the order and the
            # geometry follows the cell.
            #
            # The record fields are unsigned shorts, so the geometry is rounded
            # here rather than in the encoder - a project carries cabinet sizes
            # as floats and half-tiles land on .5.
            y_of_cell = _int(ys[(row - 1) % rows])
            geometry = {
                'x': _int(cab['x']) if cab is not None else _int(xs[col]),
                'y': y_of_cell,
                'w': _int(cab['w']) if cab is not None else pw,
                'h': _int(cab['h']) if cab is not None else ph,
            }
            if route is None:
                panels.append(dict(geometry, col=col, row=row, port_num=0,
                                   chain_order=0, hidden=True))
            else:
                panels.append(dict(geometry, col=col, row=row,
                                   port_num=route['port_num'] or 1,
                                   chain_order=route['chain_order'],
                                   hidden=route['hidden']))

    # Section bytes 10-13 are the routing the displaced cabinet would have had:
    # Sender(1) Port(1) ConnectIndex(2 LE) - the tail of a 17-byte record, minus
    # the geometry it no longer has a cell for. It is how the top-left cabinet
    # survives the slide, and it decodes cleanly on every reference file:
    # Griztronics section 0 carries 00 00 23 00 and is missing port 0 link 35,
    # its section 1 carries 00 05 06 00 and is missing port 5 link 6, and so on.
    # A top-left cell that holds no cabinet leaves the placeholder routing
    # (sender 255, port 1, link 1) - which is exactly the ff 01 01 00 that two
    # of the EDC sections carry and that used to be read as a "format" flag.
    displaced = grid.get((0, 0))
    if displaced is None or displaced['hidden']:
        marker = (0xFF, 0x01, 0x01, 0x00)
    else:
        link = displaced['chain_order'] & 0xFFFF
        marker = (canvas_index & 0xFF, (displaced['port_num'] - 1) & 0xFF,
                  link & 0xFF, (link >> 8) & 0xFF)

    return {
        'cols': cols, 'rows': rows, 'pw': pw, 'ph': ph,
        'screen_x': _int(min(xs)), 'screen_y': _int(min(ys)),
        'sc_idx': canvas_index, 'port_start': 0,
        'panels': panels,
        'marker': marker,
        # Reporting only - not read by the encoder.
        '_canvas_name': canvas.get('name'),
        '_canvas_id': canvas.get('id'),
        '_layers': [l.get('name') for l in layers],
        '_live': sum(1 for p in panels if not p['hidden']),
        '_ports': sorted({p['port_num'] for p in panels if not p['hidden']}),
    }


def _path_canvas_id(layer):
    """The canvas a group treats a layer as living on - the same
    `show_canvas_id or canvas_id` rule getPathScopeLayers applies in
    app-power.js, because that is what decides whether the app crosses."""
    return layer.get('show_canvas_id') or layer.get('canvas_id') or None


def crossing_groups(project):
    """The groups whose AUTOMATIC data routing the APP runs across the members.

    A screen group of matching panels is one bigger screen to the app: a single
    port walk over every member's cabinets, so one port can hold cabinets from
    two layers (getAutoRoutePlan, src/static/js/app-screen-info.js).

    This file does NOT do that, and cannot as it stands. Ports here are built
    one layer at a time, `routed` is keyed (col, row) INSIDE a layer - so two
    members' (0,0) name the same slot - and a crossing port would have to span
    two iterations of the layer loop and then survive the per-layer port
    renumbering below. Making it understand a crossing route is a separate job.

    So the gap is reported by name instead. The gate is transcribed from the JS
    so the two cannot disagree about which projects it applies to: at least two
    visible screen members sharing one canvas, every member the same cabinet
    RESOLUTION, and no member hand-wired (one custom member takes the whole
    group back to per-member routing). panelWatts is deliberately not checked -
    it gates the POWER walk, and a .scr carries data routing only.

    Returns [(group, [layer, ...])] in project group order.
    """
    groups = project.get('groups') or []
    layers = project.get('layers') or []
    if not isinstance(groups, list) or not groups:
        return []
    by_id = {l.get('id'): l for l in layers if isinstance(l, dict)}

    out = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        members = [by_id.get(lid) for lid in (group.get('layer_ids') or [])]
        members = [m for m in members
                   if m and (m.get('type') or 'screen') == 'screen'
                   and (m.get('panels') or [])
                   and m.get('visible', True) is not False]
        if len(members) < 2:
            continue
        # One canvas at a time: members on another canvas are a different
        # workspace and never share a route.
        by_canvas = collections.defaultdict(list)
        for m in members:
            by_canvas[_path_canvas_id(m)].append(m)
        for scope in by_canvas.values():
            if len(scope) < 2:
                continue
            if any(m.get('flowPattern') == 'custom' for m in scope):
                continue
            # ONE PROCESSOR RASTER as well as one show canvas - the JS refuses
            # to cross members laid out against different rasters, because a
            # port's pixel load and the low-latency derate are both measured
            # down one of them.
            raster = scope[0].get('canvas_id')
            if any(m.get('canvas_id') != raster for m in scope):
                continue
            width = _int(scope[0].get('cabinet_width'))
            height = _int(scope[0].get('cabinet_height'))
            if width <= 0 or height <= 0:
                continue
            if any(_int(m.get('cabinet_width')) != width
                   or _int(m.get('cabinet_height')) != height for m in scope):
                continue
            out.append((group, scope))
    return out


def warn_crossing_groups(project, warnings):
    """Say plainly, once per group, that the file's ports are NOT the app's."""
    for group, members in crossing_groups(project):
        names = ', '.join('"%s"' % (m.get('name') or m.get('id')) for m in members)
        warnings.warn(
            'group-crosses-%s' % group.get('id'),
            'screen group "%s" (%s) routes as ONE screen in the app - a single '
            'port walk across every member, so a port can carry cabinets from '
            'more than one of them. This export does NOT follow that: each '
            'member was routed on its own grid, exactly as it was before the '
            'group existed, and its ports were then renumbered per layer. The '
            'port numbers and chain order in this .scr therefore DO NOT match '
            'the Data Flow map on screen. Check every port of this group '
            'against the drawing before trusting the file in NovaLCT.'
            % (group.get('name') or group.get('id'), names))


def build_sections(project, warnings):
    """Canvases, in project order, to encoder sections. Canvases with no screen
    layers are skipped - an empty section would be a screen NovaLCT has to draw
    with nothing in it."""
    canvases = project.get('canvases') or []
    layers = project.get('layers') or []

    if not canvases:
        raise ValueError('project has no canvases')

    # Before anything is written, not after: a crossing group means the port
    # map below is a different map from the one the user is looking at, and
    # that has to be said out loud rather than discovered on site.
    warn_crossing_groups(project, warnings)

    by_canvas = collections.defaultdict(list)
    for layer in layers:
        if (layer.get('type') or 'screen') != 'screen':
            continue
        by_canvas[layer.get('canvas_id')].append(layer)

    known = {c.get('id') for c in canvases}
    for canvas_id in by_canvas:
        if canvas_id not in known:
            warnings.warn('orphan-%s' % canvas_id,
                          'screen layers reference canvas %r, which is not in the '
                          'project; they are not exported.' % canvas_id)

    sections = []
    for index, canvas in enumerate(canvases):
        canvas_layers = by_canvas.get(canvas.get('id')) or []
        if not canvas_layers:
            continue
        # The sending card index is the canvas's position in the project, so a
        # canvas with no screens leaves a gap rather than shifting every card
        # after it onto different hardware.
        section = build_canvas_section(project, canvas, index, canvas_layers, warnings)
        if section is None:
            warnings.warn('empty-%s' % canvas.get('id'),
                          'canvas "%s" has screen layers but no cabinets; skipped.'
                          % canvas.get('name'))
            continue
        sections.append(section)

    if not sections:
        raise ValueError('no canvas in this project carries any screen layers')
    return sections


# ── verification ─────────────────────────────────────────────────────────

def verify(data, sections):
    """Decode our own output and check it says what we put in.

    A file that does not survive its own decode is wrong, and this is the only
    check that runs without NovaLCT.
    """
    decoded = decode_scr(data)
    problems = []
    if len(decoded['screens']) != len(sections):
        problems.append('decoded %d sections, wrote %d'
                        % (len(decoded['screens']), len(sections)))
        return problems

    for screen, section in zip(decoded['screens'], sections):
        name = section['_canvas_name']
        if (screen['cols'], screen['rows']) != (section['cols'], section['rows']):
            problems.append('%s: grid decoded %dx%d, wrote %dx%d'
                            % (name, screen['cols'], screen['rows'],
                               section['cols'], section['rows']))
            continue
        rows = section['rows']
        # The decoder hands back binary rows; the app row is the encoder's own
        # (binary_row + 1) % rows, which is how the round trip reads them too.
        got = {}
        for p in screen['panels']:
            got[(p['col'], (p['row'] + 1) % rows)] = p
        for want in section['panels']:
            p = got.get((want['col'], want['row']))
            if p is None:
                problems.append('%s: cell (%d,%d) missing from the decode'
                                % (name, want['col'], want['row']))
                continue
            if want['col'] == section['cols'] - 1 and want['row'] == 0:
                continue  # the terminator/anchor cell is not a cabinet
            if want['hidden']:
                if p['sender'] != 255:
                    problems.append('%s: cell (%d,%d) should be a placeholder, '
                                    'decoded sender %d'
                                    % (name, want['col'], want['row'], p['sender']))
                continue
            if p['sender'] != section['sc_idx']:
                problems.append('%s: cell (%d,%d) sending card decoded %d, wrote %d'
                                % (name, want['col'], want['row'], p['sender'],
                                   section['sc_idx']))
            if p['port'] + 1 != want['port_num']:
                problems.append('%s: cell (%d,%d) port decoded %d, wrote %d'
                                % (name, want['col'], want['row'], p['port'] + 1,
                                   want['port_num']))
            if p['chain_order'] != want['chain_order']:
                problems.append('%s: cell (%d,%d) chain decoded %d, wrote %d'
                                % (name, want['col'], want['row'], p['chain_order'],
                                   want['chain_order']))
    return problems


# ── loading ──────────────────────────────────────────────────────────────

def load_project(url=None, path=None, timeout=15):
    if path:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    endpoint = url.rstrip('/')
    if not endpoint.endswith('/api/project'):
        endpoint += '/api/project'
    with urllib.request.urlopen(endpoint, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


# ── CLI ──────────────────────────────────────────────────────────────────

def export(project, out_path, warnings, quiet=False, run_verify=True):
    sections = build_sections(project, warnings)
    data = build_multi_screen_scr(sections)

    with open(out_path, 'wb') as handle:
        handle.write(data)

    if not quiet:
        print('%s  (%d bytes, %d section%s)'
              % (out_path, len(data), len(sections), '' if len(sections) == 1 else 's'))
        for section in sections:
            ports = section['_ports']
            print('  sending card %d  canvas "%s"  grid %dx%d  origin (%d,%d)  '
                  'cabinet %dx%d'
                  % (section['sc_idx'], section['_canvas_name'],
                     section['cols'], section['rows'],
                     section['screen_x'], section['screen_y'],
                     section['pw'], section['ph']))
            print('      %d live of %d cells, %d port%s (%s), layers: %s'
                  % (section['_live'], section['cols'] * section['rows'],
                     len(ports), '' if len(ports) == 1 else 's',
                     _range_text(ports), ', '.join(str(n) for n in section['_layers'])))

    problems = verify(data, sections) if run_verify else []
    if not quiet:
        if run_verify:
            if problems:
                print('\nRound trip FAILED - the file does not decode to what was written:')
                for problem in problems[:20]:
                    print('  %s' % problem)
                if len(problems) > 20:
                    print('  ... and %d more' % (len(problems) - 20))
            else:
                print('\nRound trip OK: decoded back to the same cabinets, ports and chains.')
        if warnings.items:
            print('\n%d warning%s:' % (len(warnings), '' if len(warnings) == 1 else 's'))
            for item in warnings.items:
                print('  - %s' % item)
    return sections, problems


def _range_text(ports):
    if not ports:
        return 'none'
    if len(ports) == 1:
        return str(ports[0])
    if ports == list(range(ports[0], ports[-1] + 1)):
        return '%d-%d' % (ports[0], ports[-1])
    return ', '.join(str(p) for p in ports)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Export a project as a NovaStar .scr sending card map.')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--url', help='base URL of the running app, e.g. http://localhost:8061')
    source.add_argument('--project', help='path to a saved project JSON file')
    parser.add_argument('--out', required=True, help='path to write the .scr to')
    parser.add_argument('--no-verify', action='store_true',
                        help='skip decoding the output back and checking it')
    parser.add_argument('--quiet', action='store_true', help='only report failures')
    args = parser.parse_args(argv)

    try:
        project = load_project(url=args.url, path=args.project)
    except Exception as exc:
        print('could not load the project: %s' % exc, file=sys.stderr)
        return 2

    warnings = Warnings()
    try:
        _, problems = export(project, args.out, warnings,
                             quiet=args.quiet, run_verify=not args.no_verify)
    except ValueError as exc:
        print('cannot export: %s' % exc, file=sys.stderr)
        return 2

    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
