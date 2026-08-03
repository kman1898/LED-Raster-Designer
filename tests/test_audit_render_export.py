"""v0.10.9 audit - RENDERING AND EXPORT.

An adversarial pass over what v0.10.9 draws on screen and what it writes into
the files a crew takes to site. Written as a standalone audit file so nothing
here can be mistaken for the feature's own tests.

Two halves:

  * Export (pure Python, no browser). Resolume XML is parsed back and compared
    against hand-computed geometry; the PSD is written and read back with
    pytoshop, never asserted on "it did not raise".

  * Canvas (Playwright, synthetic projects). Every assertion reads RECORDED ctx
    calls, transformed through the live CTM into world coordinates, so what is
    asserted is where the ink actually landed. Nothing reads el.style - theme.css
    uses !important and inline styles never render.

Tests named test_bug_* record a defect: they assert the WRONG behaviour that is
in the tree today, with the correct value spelled out in the docstring, so the
file passes on today's code and turns red the moment a fix lands. Tests named
test_ok_* pin behaviour that was checked and found correct.

The six CANVAS findings have since been FIXED, so their tests were flipped to
assert the correct behaviour and renamed test_canvas_ok_*; each keeps a
docstring saying what it used to do and why. All of them had one cause -
rotation was ranked and bounded in unrotated space and then drawn inside a
rotation transform - and one fix, the _layerDrawFrame / _drawnPanelRect pair in
canvas.js that every consumer now maps a cabinet through. The EXPORT findings
above are not touched by any of that and still assert today's behaviour.

Run the export half alone (fast, no server):
    python -m pytest tests/test_audit_render_export.py -q -k "not canvas"
"""

import io
import random
import re
import sys
import os
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import app as app_module
from app import (
    _build_panels,
    _compute_layers_contour,
    _export_unit_bounds,
    _export_unit_needs_polygon,
    _export_units,
    _layer_has_hidden_panels,
    generate_resolume_xml,
    render_unit_to_image,
)


# ── export helpers ────────────────────────────────────────────────────────

def _screen(lid, name, rows, cols, cw=128, ch=128, ox=0, oy=0, states=None,
            canvas_id=None, visible=True, rgb=(255, 0, 0)):
    """A screen layer with real _build_panels geometry, one flat colour."""
    layer = {
        'id': lid, 'name': name, 'type': 'screen', 'visible': visible,
        'rows': rows, 'columns': cols,
        'cabinet_width': cw, 'cabinet_height': ch,
        'offset_x': ox, 'offset_y': oy,
        'canvas_id': canvas_id,
        'color1': {'r': rgb[0], 'g': rgb[1], 'b': rgb[2]},
        'color2': {'r': rgb[0], 'g': rgb[1], 'b': rgb[2]},
        'show_panel_borders': False,
    }
    layer['panels'] = _build_panels(layer, dict(states or {}))
    return layer


def _group(gid, name, layers):
    for layer in layers:
        layer['group_id'] = gid
    return {'id': gid, 'name': name, 'layer_ids': [l['id'] for l in layers]}


def _project(layers, groups=None, canvases=None, raster=(1920, 1080)):
    project = {
        'name': 'Proj', 'layers': layers,
        'raster_width': raster[0], 'raster_height': raster[1],
    }
    if groups is not None:
        project['groups'] = groups
    if canvases is not None:
        project['canvases'] = canvases
    return project


def _xml(project):
    random.seed(4242)
    return generate_resolume_xml(
        project, 'Proj', project['raster_width'], project['raster_height'])


def _shapes(xml):
    """(tag, name) for every Slice/Polygon in document order."""
    return re.findall(
        r'<(Slice|Polygon) uniqueId="\d+"[^>]*>\s*<Params name="Common">\s*'
        r'<Param name="Name" T="STRING" default="Layer" value="([^"]*)"', xml)


def _output_rects(xml):
    out = []
    for block in re.findall(r'<OutputRect orientation="0">(.*?)</OutputRect>',
                            xml, re.S):
        pts = [(float(x), float(y))
               for x, y in re.findall(r'<v x="(-?[\d.]+)" y="(-?[\d.]+)"/>', block)]
        out.append((pts[0][0], pts[0][1], pts[2][0], pts[2][1]))
    return out


def _contours(xml):
    blocks = re.findall(r'<InputContour closed="1">\s*<points>(.*?)</points>',
                        xml, re.S)
    return [
        [(int(x), int(y))
         for x, y in re.findall(r'<v x="(-?\d+)" y="(-?\d+)"/>', b)]
        for b in blocks
    ]


def _poly_area(points):
    """Shoelace area of a traced contour, in square pixels."""
    total = 0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _lit_area(layers):
    """Square pixels of actual LED surface across these layers (no overlaps)."""
    covered = set()
    for layer in layers:
        for p in layer['panels']:
            if p.get('hidden') or p.get('blank'):
                continue
            covered.add((int(p['x']), int(p['y']),
                         int(p['x'] + p['width']), int(p['y'] + p['height'])))
    # rectangles here are chosen non-overlapping in every test that calls this
    return sum((x2 - x1) * (y2 - y1) for (x1, y1, x2, y2) in covered)


def _psd_records(project):
    """Write the PSD for this project and read the layer records back."""
    pytoshop = pytest.importorskip("pytoshop", reason="pytoshop not installed")
    saved = app_module.current_project
    try:
        app_module.current_project = project
        buf = app_module.create_psd_for_view('pixel-map', 'Proj', False)
    finally:
        app_module.current_project = saved
    psd = pytoshop.PsdFile.read(io.BytesIO(buf.getvalue()))
    return psd.layer_and_mask_info.layer_info.layer_records


# ══════════════════════════════════════════════════════════════════════════
# RESOLUME - the shape a group actually maps to
# ══════════════════════════════════════════════════════════════════════════

def test_fixed_a_group_with_a_gap_exports_one_shape_per_wall():
    """WAS: two members with air between them shipped as ONE plain <Slice>
    spanning the union, gap included - Resolume mapped content straight across
    the hole and a third of the picture was thrown into the air between the
    walls.

    NOW: one shape per island. Left wall 0..256 and right wall 512..768 each
    get their own Slice at their own coordinates, both carrying the GROUP's
    name, and nothing claims the 256 px of nothing between them. Input and
    output rectangles are still equal, so every pixel lands exactly where the
    pixel map says it does.
    """
    a = _screen(1, 'Left', 2, 2)
    b = _screen(2, 'Right', 2, 2, ox=512)
    g = _group('g1', 'Main Wall', [a, b])
    xml = _xml(_project([a, b], groups=[g]))

    assert _shapes(xml) == [('Slice', 'Main Wall'), ('Slice', 'Main Wall')]
    assert _output_rects(xml) == [(0.0, 0.0, 256.0, 256.0),
                                  (512.0, 0.0, 768.0, 256.0)]
    # Exactly the lit surface is claimed, no more: 2 x 65536 px2.
    assert sum((x2 - x1) * (y2 - y1) for x1, y1, x2, y2 in _output_rects(xml)) \
        == _lit_area([a, b]) == 131072


def test_fixed_the_trace_of_a_split_group_keeps_every_island():
    """WAS the root cause of the test above: _compute_layers_contour walked
    the boundary from the top-right vertex and STOPPED the moment it closed
    that ring, so a second disconnected island was never visited. The
    four-vertex answer then read as "this is a rectangle".

    NOW _compute_layers_islands returns a ring per island, in reading order,
    and every export path goes through it.
    """
    a = _screen(1, 'Left', 2, 2)
    b = _screen(2, 'Right', 2, 2, ox=512)
    islands = app_module._compute_layers_islands([a, b])
    assert islands == [
        [(256, 0), (0, 0), (0, 256), (256, 256)],
        [(768, 0), (512, 0), (512, 256), (768, 256)],
    ]
    assert sum(_poly_area(ring) for ring in islands) == _lit_area([a, b])
    # Each island is a plain rectangle, so each is a Slice, not a Polygon.
    assert [needs_poly for needs_poly, _c, _b
            in app_module._export_unit_shapes([a, b])] == [False, False]


def test_fixed_a_stacked_group_with_a_vertical_gap_splits_too():
    """Same defect on the axis a mixed-cabinet wall is usually built on - a
    header strip flown above the main wall. Two shapes, 0..256 and 512..768
    in Y, and no shape over the air between them."""
    a = _screen(1, 'Top', 2, 4)
    b = _screen(2, 'Bottom', 2, 4, oy=512)
    g = _group('g2', 'Stacked', [a, b])
    assert len(app_module._compute_layers_islands([a, b])) == 2
    xml = _xml(_project([a, b], groups=[g]))
    assert _shapes(xml) == [('Slice', 'Stacked'), ('Slice', 'Stacked')]
    assert _output_rects(xml) == [(0.0, 0.0, 512.0, 256.0),
                                  (0.0, 512.0, 512.0, 768.0)]
    # The UNION bounds are unchanged - they are still what a caller asking for
    # the whole unit's extent gets.
    assert _export_unit_bounds([a, b]) == {
        'x': 0.0, 'y': 0.0, 'width': 512.0, 'height': 768.0}


def test_fixed_a_third_detached_member_is_exported_too():
    """WAS: three members, two touching and one parked to the right - the
    contour kept only the parked one and the Slice spanned all three, so the
    touching pair vanished from the trace.

    NOW: two islands (the touching pair is one wall), two shapes.
    """
    a = _screen(1, 'A', 2, 2)
    b = _screen(2, 'B', 2, 2, ox=256)
    c = _screen(3, 'C', 2, 2, ox=1024)
    g = _group('g3', 'Three', [a, b, c])
    assert app_module._compute_layers_islands([a, b, c]) == [
        [(512, 0), (0, 0), (0, 256), (512, 256)],
        [(1280, 0), (1024, 0), (1024, 256), (1280, 256)],
    ]
    xml = _xml(_project([a, b, c], groups=[g]))
    assert _output_rects(xml) == [(0.0, 0.0, 512.0, 256.0),
                                  (1024.0, 0.0, 1280.0, 256.0)]
    assert _export_unit_bounds([a, b, c])['width'] == 1280.0


def test_fixed_a_single_screen_split_by_a_hidden_column_keeps_both_halves():
    """WAS PRE-EXISTING (not a group regression) - the same single-ring trace.
    One 1x5 screen with the middle cabinet deleted mapped only the right-hand
    two, and the left two got no Resolume slice at all, so they went black.

    NOW: a shape per half, 0..256 and 384..640.
    """
    a = _screen(1, 'Solo', 1, 5, states={(0, 2): {'hidden': True}})
    assert _layer_has_hidden_panels(a) is True
    assert app_module._compute_layers_islands([a]) == [
        [(256, 0), (0, 0), (0, 128), (256, 128)],
        [(640, 0), (384, 0), (384, 128), (640, 128)],
    ]
    xml = _xml(_project([a]))
    assert _shapes(xml) == [('Slice', 'Solo'), ('Slice', 'Solo')]
    assert _output_rects(xml) == [(0.0, 0.0, 256.0, 128.0),
                                  (384.0, 0.0, 640.0, 128.0)]


def test_fixed_a_corner_touching_group_traces_two_simple_rings():
    """WAS: two members meeting only at a corner produced a contour that passed
    through the shared vertex TWICE - a figure-of-eight, and how a warper fills
    a self-intersecting polygon is undefined.

    NOW: corner contact is not connection (cells are grouped 4-connected), so
    the two cabinets are two islands and each traces a simple rectangle. The
    shared vertex (256, 256) appears once in each.
    """
    a = _screen(1, 'A', 2, 2)
    b = _screen(2, 'B', 2, 2, ox=256, oy=256)
    islands = app_module._compute_layers_islands([a, b])
    assert islands == [
        [(256, 0), (0, 0), (0, 256), (256, 256)],
        [(512, 256), (256, 256), (256, 512), (512, 512)],
    ]
    for ring in islands:
        assert ring.count((256, 256)) <= 1, ring
        assert len(set(ring)) == len(ring)


def test_fixed_a_blanked_cabinet_makes_a_LONE_screen_a_polygon():
    """WAS: v0.10.9 taught the CONTOUR that a blank cabinet is not LED but left
    the shape DECISION for a lone screen on the old hidden-only test, so a
    single screen with a blanked corner traced a correct six-vertex outline
    that was then thrown away and shipped as a full rectangle.

    NOW: the same six-vertex Polygon the identical wall gets the moment it is
    grouped (next test).
    """
    a = _screen(1, 'Solo', 2, 2, states={(0, 0): {'blank': True}})
    outline = [(256, 0), (128, 0), (128, 128), (0, 128), (0, 256), (256, 256)]
    assert _compute_layers_contour([a]) == outline
    assert _export_unit_needs_polygon([a]) is True
    xml = _xml(_project([a]))
    assert _shapes(xml) == [('Polygon', 'Solo')]
    assert _contours(xml) == [outline]
    # The bounding box is unmoved; only the shape inside it changed.
    assert _output_rects(xml) == [(0.0, 0.0, 256.0, 256.0)]


def test_fixed_grouping_a_wall_no_longer_changes_the_shape_it_exports():
    """WAS: the SAME physical wall exported as a rectangle ungrouped and as a
    polygon grouped, purely because of the lone-layer shortcut above - two
    crews with the same wall got two different Resolume files depending on
    whether somebody pressed Group Screens.
    """
    a = _screen(1, 'A', 2, 2, states={(0, 0): {'blank': True}})
    b = _screen(2, 'B', 2, 2, ox=256)
    assert _export_unit_needs_polygon([a]) is True        # ungrouped -> Polygon
    assert _export_unit_needs_polygon([a, b]) is True     # grouped   -> Polygon
    grouped = _xml(_project([a, b], groups=[_group('g', 'W', [a, b])]))
    assert [t for t, _ in _shapes(grouped)] == ['Polygon']
    # And a screen with no knocked-out cabinet is still a plain Slice, grouped
    # or not - the load-bearing no-change case.
    plain = _screen(3, 'P', 2, 2)
    assert _export_unit_needs_polygon([plain]) is False


def test_fixed_an_ampersand_in_a_group_name_is_escaped():
    """WAS unparseable (pre-existing for layer names; a group name was a new
    way in). The canvas name was escaped; the shape name was interpolated raw
    in _resolume_slice and _resolume_polygon. "Left & Right" is a completely
    normal name for a wall.
    """
    a = _screen(1, 'A', 2, 2)
    b = _screen(2, 'B', 2, 2, ox=256)
    g = _group('g5', 'Left & Right', [a, b])
    xml = _xml(_project([a, b], groups=[g]))
    assert 'value="Left &amp; Right"' in xml
    assert 'value="Left & Right"' not in xml
    ET.fromstring(xml)          # Resolume can open it

    # The same for a plain screen name, and for the angle brackets and quote.
    hostile = _screen(3, 'A & B <"C">', 2, 2)
    xml = _xml(_project([hostile]))
    assert 'value="A &amp; B &lt;&quot;C&quot;&gt;"' in xml
    ET.fromstring(xml)


# ── Resolume: what IS right ───────────────────────────────────────────────

def test_ok_a_rectangular_group_is_one_slice_named_for_the_group():
    """20x9 of 128 px stacked on 40x2 of 64 px -> exactly 2560 x 1280."""
    jp5 = _screen(1, 'JP5', 9, 20)
    half = _screen(2, 'Half', 2, 40, cw=64, ch=64, oy=1152)
    g = _group('g', 'Main Wall', [jp5, half])
    xml = _xml(_project([jp5, half], groups=[g], raster=(4096, 2160)))
    assert _shapes(xml) == [('Slice', 'Main Wall')]
    assert _output_rects(xml) == [(0.0, 0.0, 2560.0, 1280.0)]
    assert 'JP5' not in xml and 'Half' not in xml
    # no spurious vertex on the seam between two cabinet sizes
    assert _compute_layers_contour([jp5, half]) == [
        (2560, 0), (0, 0), (0, 1280), (2560, 1280)]


def test_ok_an_l_shaped_group_is_one_polygon_following_only_the_cabinets():
    """4x2 across the top with 2x2 hung under the left half.

    Hand-computed: the outline is (512,0) (0,0) (0,512) (256,512) (256,256)
    (512,256); enclosed area 196608 px2, which is exactly the lit surface
    (8 + 4 cabinets of 128x128).
    """
    a = _screen(1, 'A', 2, 4)
    b = _screen(2, 'B', 2, 2, oy=256)
    g = _group('g', 'Ell', [a, b])
    xml = _xml(_project([a, b], groups=[g]))
    assert _shapes(xml) == [('Polygon', 'Ell')]
    contour = _contours(xml)[0]
    assert contour == [(512, 0), (0, 0), (0, 512), (256, 512), (256, 256), (512, 256)]
    assert _poly_area(contour) == 12 * 128 * 128 == _lit_area([a, b])
    # the InputRect/OutputRect still bound the whole wall
    assert _output_rects(xml) == [(0.0, 0.0, 512.0, 512.0)]


def test_ok_a_plus_shaped_group_traces_all_twelve_vertices():
    """Two overlapping bars. The overlap must be counted once, not twice."""
    a = _screen(1, 'A', 1, 3, oy=128)
    b = _screen(2, 'B', 3, 1, ox=128)
    contour = _compute_layers_contour([a, b])
    assert len(contour) == 12
    # 3 + 3 cabinets minus the shared middle one = 5 cabinets of 128x128
    assert _poly_area(contour) == 5 * 128 * 128 == 81920


def test_ok_a_half_tile_column_shrinks_the_exported_rectangle():
    """A half-WIDTH left column makes a 2x2 of 128 px 192 px wide, not 256."""
    states = {(0, 0): {'halfTile': 'width'}, (1, 0): {'halfTile': 'width'}}
    a = _screen(1, 'Half', 2, 2, states=states)
    assert [(p['x'], p['width']) for p in a['panels']] == [
        (0.0, 64.0), (64.0, 128.0), (0.0, 64.0), (64.0, 128.0)]
    assert _compute_layers_contour([a]) == [(192, 0), (0, 0), (0, 256), (192, 256)]
    xml = _xml(_project([a]))
    assert _output_rects(xml) == [(0.0, 0.0, 192.0, 256.0)]


def test_ok_a_half_tile_seam_inside_a_group_tiles_flush():
    """The half-width member is 192 wide, so its neighbour at x=192 joins it
    with no vertex on the seam: one 448 x 256 rectangle."""
    states = {(0, 0): {'halfTile': 'width'}, (1, 0): {'halfTile': 'width'}}
    a = _screen(1, 'A', 2, 2, states=states)
    b = _screen(2, 'B', 2, 2, ox=192)
    assert _compute_layers_contour([a, b]) == [
        (448, 0), (0, 0), (0, 256), (448, 256)]
    assert _export_unit_needs_polygon([a, b]) is False


def test_ok_a_hidden_member_is_left_out_of_the_resolume_export():
    """Resolume filters on layer.visible before units are built
    (src/app.py:2628), so a hidden section neither draws nor stretches the
    slice."""
    a = _screen(1, 'A', 2, 2)
    b = _screen(2, 'B', 2, 2, ox=256, visible=False)
    g = _group('g', 'Wall', [a, b])
    xml = _xml(_project([a, b], groups=[g]))
    assert _shapes(xml) == [('Slice', 'Wall')]
    assert _output_rects(xml) == [(0.0, 0.0, 256.0, 256.0)]


def test_ok_a_group_of_one_keeps_the_lone_screens_geometry():
    """Only the NAME changes; every coordinate is the ungrouped export's."""
    lone = _screen(1, 'Solo', 2, 3)
    plain = _xml(_project([lone]))
    grouped_layer = _screen(1, 'Solo', 2, 3)
    g = _group('g', 'Just One', [grouped_layer])
    grouped = _xml(_project([grouped_layer], groups=[g]))
    assert _shapes(plain) == [('Slice', 'Solo')]
    assert _shapes(grouped) == [('Slice', 'Just One')]
    assert _output_rects(plain) == _output_rects(grouped)
    assert plain.replace('"Solo"', '"X"') == grouped.replace('"Just One"', '"X"')


def test_ok_ungrouped_members_still_export_as_two_shapes():
    """The load-bearing no-change case: no groups array, two Slices, own
    names, own rectangles."""
    a = _screen(1, 'A', 2, 2)
    b = _screen(2, 'B', 2, 2, ox=256)
    xml = _xml(_project([a, b]))
    assert _shapes(xml) == [('Slice', 'A'), ('Slice', 'B')]
    assert _output_rects(xml) == [(0.0, 0.0, 256.0, 256.0),
                                  (256.0, 0.0, 512.0, 256.0)]


def test_ok_a_group_split_across_canvases_exports_once_per_canvas():
    """Members scoped to different canvases stay with their own canvas and
    each canvas's shape uses only the members present there."""
    a = _screen(1, 'A', 2, 2, canvas_id='c1')
    b = _screen(2, 'B', 2, 2, canvas_id='c2')
    g = _group('g', 'Split Wall', [a, b])
    canvases = [
        {'id': 'c1', 'name': 'Canvas 1', 'workspace_x': 0, 'workspace_y': 0,
         'raster_width': 1920, 'raster_height': 1080, 'visible': True},
        {'id': 'c2', 'name': 'Canvas 2', 'workspace_x': 2000, 'workspace_y': 0,
         'raster_width': 1920, 'raster_height': 1080, 'visible': True},
    ]
    xml = _xml(_project([a, b], groups=[g], canvases=canvases))
    assert _shapes(xml) == [('Slice', 'Split Wall'), ('Slice', 'Split Wall')]
    assert _output_rects(xml) == [(0.0, 0.0, 256.0, 256.0),
                                  (0.0, 0.0, 256.0, 256.0)]


# ══════════════════════════════════════════════════════════════════════════
# PSD - one Photoshop layer per group
# ══════════════════════════════════════════════════════════════════════════

def test_fixed_a_hidden_group_member_no_longer_paints_into_the_psd():
    """WAS: render_unit_to_image composited every member without ever looking
    at layer.visible, so a hidden section arrived in Photoshop fully opaque and
    widened the record over ground it does not occupy. The PSD handed to
    graphics showed a section the designer was told had been struck from the
    build. Ungrouped screens behaved correctly, so this was a group regression.

    NOW: a hidden member contributes no pixels and does not widen the layer,
    which is what Resolume has always done (it filters on visible before units
    are built).
    """
    vis = _screen(1, 'Vis', 2, 2, rgb=(255, 0, 0))
    hid = _screen(2, 'Hid', 2, 2, ox=256, visible=False, rgb=(0, 255, 0))
    img = render_unit_to_image([vis, hid], 1024, 512, include_borders=False)
    assert img.getpixel((64, 64)) == (255, 0, 0, 255)
    assert img.getpixel((320, 64)) == (0, 0, 0, 0)

    g = _group('g1', 'Main Wall', [vis, hid])
    records = _psd_records(_project([vis, hid], groups=[g], raster=(1024, 512)))
    assert len(records) == 1
    rec = records[0]
    assert rec.name == 'Main Wall'
    assert rec.opacity == 255
    assert (rec.left, rec.top, rec.right, rec.bottom) == (0, 0, 256, 256)


def test_fixed_a_group_with_every_member_hidden_keeps_its_pixels():
    """The other half of the rule: a unit with NOTHING visible is emitted at
    opacity 0 with its pixels intact, exactly as an ungrouped hidden screen
    always has been - switch it back on in Photoshop and the wall is there.
    Only a member hidden ALONGSIDE a visible one is dropped."""
    a = _screen(1, 'A', 2, 2, visible=False, rgb=(255, 0, 0))
    b = _screen(2, 'B', 2, 2, ox=256, visible=False, rgb=(0, 255, 0))
    img = render_unit_to_image([a, b], 1024, 512, include_borders=False)
    assert img.getpixel((64, 64)) == (255, 0, 0, 255)
    assert img.getpixel((320, 64)) == (0, 255, 0, 255)

    g = _group('g1', 'Dark Wall', [a, b])
    records = _psd_records(_project([a, b], groups=[g], raster=(1024, 512)))
    assert [(r.name, r.opacity) for r in records] == [('Dark Wall', 0)]
    assert (records[0].left, records[0].right) == (0, 512)


def test_ok_an_ungrouped_hidden_screen_is_still_marked_invisible_in_the_psd():
    """The baseline the case above regressed from: ungrouped, the hidden
    screen is its own record at opacity 0 and only its own size."""
    vis = _screen(1, 'Vis', 2, 2, rgb=(255, 0, 0))
    hid = _screen(2, 'Hid', 2, 2, ox=256, visible=False, rgb=(0, 255, 0))
    records = _psd_records(_project([vis, hid], raster=(1024, 512)))
    assert [(r.name, r.opacity) for r in records] == [('Vis', 255), ('Hid', 0)]
    assert [(r.left, r.right) for r in records] == [(0, 256), (256, 512)]


def test_ok_a_group_is_one_psd_layer_at_the_hand_computed_union():
    """Mixed sizes: 4x2 of 128 px (512x256) with 8x2 of 64 px (512x128)
    underneath -> one record named for the group, 0,0 - 512,384."""
    big = _screen(1, 'Big', 2, 4, rgb=(255, 0, 0))
    small = _screen(2, 'Small', 2, 8, cw=64, ch=64, oy=256, rgb=(0, 0, 255))
    g = _group('g', 'One Wall', [big, small])
    records = _psd_records(_project([big, small], groups=[g], raster=(1024, 512)))
    assert len(records) == 1
    rec = records[0]
    assert rec.name == 'One Wall'
    assert (rec.left, rec.top, rec.right, rec.bottom) == (0, 0, 512, 384)


def test_ok_a_group_psd_layer_carries_both_members_pixels_undoubled():
    """Composited once each, no member painted over another's cabinets."""
    big = _screen(1, 'Big', 2, 4, rgb=(255, 0, 0))
    small = _screen(2, 'Small', 2, 8, cw=64, ch=64, oy=256, rgb=(0, 0, 255))
    img = render_unit_to_image([big, small], 1024, 512, include_borders=False)
    assert img.getpixel((10, 10)) == (255, 0, 0, 255)       # big member
    assert img.getpixel((10, 300)) == (0, 0, 255, 255)      # small member
    assert img.getpixel((600, 10)) == (0, 0, 0, 0)          # outside the wall
    assert img.getpixel((10, 400)) == (0, 0, 0, 0)          # below the wall


def test_ok_export_units_keeps_the_first_members_slot_and_emits_once():
    """Drawing order does not shuffle, and a group is emitted exactly once
    however its members are interleaved with ungrouped screens."""
    a = _screen(1, 'A', 1, 1)
    b = _screen(2, 'B', 1, 1)
    c = _screen(3, 'C', 1, 1)
    g = _group('g', 'Wall', [a, c])
    units = _export_units(_project([a, b, c], groups=[g]), [a, b, c])
    assert [(name, [l['id'] for l in members]) for name, members in units] == [
        ('Wall', [1, 3]), ('B', [2])]


# ══════════════════════════════════════════════════════════════════════════
# CANVAS - what is drawn, in world coordinates
# ══════════════════════════════════════════════════════════════════════════
#
# Every recorder below pushes the drawn point through the LIVE ctx transform,
# so what is asserted is where the ink landed in the workspace, not the
# argument some function happened to pass. The renderer's base transform is
# setTransform(zoom, 0, 0, zoom, panX, panY) (canvas.js:2952) and the harness
# pins zoom=1 / pan=0, so CTM(point) IS the world point.

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


AUDIT_HELPERS_JS = r"""
window.__ar = {
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
            lowLatency: false,
            color1: { r: 64, g: 70, b: 128 }, color2: { r: 149, g: 156, b: 184 },
            show_numbers: true, number_size: 30,
            show_panel_borders: true, panel_border_width: 2,
            border_color: '#ffffff', rotation: 0,
            flowPattern: 'tl-h', portMappingMode: 'organized',
            powerFlowPattern: 'tl-h', powerOrganized: true, powerMaximize: false,
        }, opts || {});
        const panels = [];
        for (let r = 0; r < o.rows; r++) {
            for (let c = 0; c < o.columns; c++) {
                panels.push({
                    id: r * o.columns + c + 1, number: r * o.columns + c + 1,
                    row: r, col: c,
                    x: o.offset_x + c * o.cabinet_width,
                    y: o.offset_y + r * o.cabinet_height,
                    width: o.cabinet_width, height: o.cabinet_height,
                    hidden: false, blank: false, halfTile: 'none',
                    is_color1: (r + c) % 2 === 0,
                });
            }
        }
        o.panels = panels;
        return o;
    },

    canvas(id, opts) {
        return Object.assign({
            id: id, name: 'Canvas ' + id,
            workspace_x: 0, workspace_y: 0,
            show_workspace_x: 0, show_workspace_y: 0,
            raster_width: 8192, raster_height: 8192,
            show_raster_width: 8192, show_raster_height: 8192,
            color: '#ff0000', visible: true,
        }, opts || {});
    },

    project(layers, groups, canvases) {
        return {
            layers: layers,
            groups: groups || [],
            canvases: canvases || [this.canvas('c1')],
            active_canvas_id: (canvases && canvases[0] && canvases[0].id) || 'c1',
        };
    },

    group(layers, opts) {
        return Object.assign({
            id: 'g1', name: 'Main Wall', layer_ids: layers.map(l => l.id),
        }, opts || {});
    },

    withProject(cfg, fn) {
        const app = window.app;
        const r = window.canvasRenderer;
        const saved = {
            project: app.project, currentLayer: app.currentLayer,
            selectedLayerIds: app.selectedLayerIds,
            history: app.history, historyIndex: app.historyIndex,
            updateLayers: app.updateLayers, renderLayers: app.renderLayers,
            loadLayerToInputs: app.loadLayerToInputs,
            loadTextLayerToInputs: app.loadTextLayerToInputs,
            saveClientSideProperties: app.saveClientSideProperties,
            activateCanvas: app._activateCanvasForLayer,
            customSelection: app.customSelection,
            powerCustomSelection: app.powerCustomSelection,
            viewMode: r.viewMode, zoom: r.zoom, panX: r.panX, panY: r.panY,
            magneticSnap: r.magneticSnap, exportMode: r.exportMode,
            showGrid: r.showGrid,
        };
        app.updateLayers = () => {};
        app.renderLayers = () => {};
        app.loadLayerToInputs = () => {};
        app.loadTextLayerToInputs = () => {};
        app.saveClientSideProperties = () => {};
        app._activateCanvasForLayer = () => {};
        app.project = this.project(cfg.layers, cfg.groups, cfg.canvases);
        app.currentLayer = cfg.currentLayer || null;
        app.selectedLayerIds = new Set();
        if (cfg.customSelection) app.customSelection = new Set(cfg.customSelection);
        if (cfg.powerCustomSelection) app.powerCustomSelection = new Set(cfg.powerCustomSelection);
        app.history = []; app.historyIndex = -1;
        r.viewMode = cfg.viewMode || 'pixel-map';
        r.zoom = cfg.zoom === undefined ? 1 : cfg.zoom;
        r.panX = 0; r.panY = 0;
        r.magneticSnap = false;
        r.showGrid = false;
        r.exportMode = !!cfg.exportMode;
        try {
            return fn();
        } finally {
            app.project = saved.project;
            app.currentLayer = saved.currentLayer;
            app.selectedLayerIds = saved.selectedLayerIds;
            app.history = saved.history; app.historyIndex = saved.historyIndex;
            app.updateLayers = saved.updateLayers;
            app.renderLayers = saved.renderLayers;
            app.loadLayerToInputs = saved.loadLayerToInputs;
            app.loadTextLayerToInputs = saved.loadTextLayerToInputs;
            app.saveClientSideProperties = saved.saveClientSideProperties;
            app._activateCanvasForLayer = saved.activateCanvas;
            app.customSelection = saved.customSelection;
            app.powerCustomSelection = saved.powerCustomSelection;
            r.viewMode = saved.viewMode;
            r.zoom = saved.zoom; r.panX = saved.panX; r.panY = saved.panY;
            r.magneticSnap = saved.magneticSnap;
            r.showGrid = saved.showGrid;
            r.exportMode = saved.exportMode;
            r.isDraggingLayer = false; r.isSelectingLayers = false;
            r.layerSelectionRect = null;
            r.render();
        }
    },

    // ── recorders: everything is returned in WORLD coords, by pushing the
    // drawn point through the live CTM. With zoom=1 / pan=0 the renderer's
    // base transform is the identity, so CTM(point) IS the world point.
    _rec(names, collect) {
        const r = window.canvasRenderer;
        const ctx = r.ctx;
        const originals = {};
        const out = [];
        const xf = (x, y) => {
            const m = ctx.getTransform();
            return { x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f };
        };
        names.forEach(n => { originals[n] = ctx[n]; });
        collect(ctx, out, xf, originals);
        try { r.render(); } finally {
            names.forEach(n => { ctx[n] = originals[n]; });
        }
        return out;
    },

    // Circles, in world coords, with the radius scaled by the CTM.
    arcs() {
        return this._rec(['arc'], (ctx, out, xf, orig) => {
            ctx.arc = function (x, y, radius, a, b, c) {
                const m = ctx.getTransform();
                const p = xf(x, y);
                out.push({ x: Math.round(p.x), y: Math.round(p.y),
                           r: Math.round(radius * Math.hypot(m.a, m.b)) });
                return orig.arc.call(ctx, x, y, radius, a, b, c);
            };
        });
    },

    // Every moveTo/lineTo pair as a world-space segment. `overlay` records
    // whether the renderer was inside the post-loop cross-member pass at the
    // time, which is how the crossing-cable tests below pick their segments out
    // without guessing from lengths or draw order.
    segments() {
        let cur = null;
        const r = window.canvasRenderer;
        return this._rec(['moveTo', 'lineTo'], (ctx, out, xf, orig) => {
            ctx.moveTo = function (x, y) {
                cur = xf(x, y);
                return orig.moveTo.call(ctx, x, y);
            };
            ctx.lineTo = function (x, y) {
                const p = xf(x, y);
                if (cur) out.push({ x1: Math.round(cur.x), y1: Math.round(cur.y),
                                    x2: Math.round(p.x), y2: Math.round(p.y),
                                    overlay: !!r._crossMemberPass });
                cur = p;
                return orig.lineTo.call(ctx, x, y);
            };
        });
    },

    // The cabinet-to-cabinet run of a crossing port/circuit: the segments the
    // post-loop overlay pass drew, minus the arrowheads (which are shorter
    // than a cabinet pitch).
    overlayCable(minLen) {
        const z = window.canvasRenderer.zoom;
        return this.segments()
            .filter(s => s.overlay
                && Math.hypot(s.x2 - s.x1, s.y2 - s.y1) >= (minLen || 100) * z)
            .map(s => ({ x1: s.x1, y1: s.y1, x2: s.x2, y2: s.y2 }));
    },

    // Every fillRect, in world coords.
    fills() {
        return this._rec(['fillRect'], (ctx, out, xf, orig) => {
            ctx.fillRect = function (x, y, w, h) {
                const a = xf(x, y), b = xf(x + w, y + h);
                out.push({ x: Math.round(Math.min(a.x, b.x)),
                           y: Math.round(Math.min(a.y, b.y)),
                           w: Math.round(Math.abs(b.x - a.x)),
                           h: Math.round(Math.abs(b.y - a.y)),
                           style: String(ctx.fillStyle) });
                return orig.fillRect.call(ctx, x, y, w, h);
            };
        });
    },

    // Every string drawn, with its world position.
    texts() {
        return this._rec(['fillText'], (ctx, out, xf, orig) => {
            ctx.fillText = function (t, x, y, w) {
                const p = xf(x, y);
                out.push({ t: String(t), x: Math.round(p.x), y: Math.round(p.y) });
                return orig.fillText.call(ctx, t, x, y, w);
            };
        });
    },
};

"""


@pytest.fixture(scope="module")
def canvas(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    page = context.new_page()
    page.goto(e2e_server, wait_until='domcontentloaded')
    page.wait_for_timeout(2000)   # socket connect + app init
    page.evaluate(AUDIT_HELPERS_JS)
    return page


def _js(canvas, body):
    return canvas.evaluate("() => { const A = window.__ar;\n%s\n}" % body)


# ── the circle-and-X test pattern ─────────────────────────────────────────

MIXED_PAIR_JS = """
    const a = A.screen({ id: 1, name: 'A', columns: 4, rows: 2,
                         show_circle_with_x: true, rotation: ROT_A });
    const b = A.screen({ id: 2, name: 'B', columns: 8, rows: 2,
                         cabinet_width: 64, cabinet_height: 64, offset_y: 256,
                         show_circle_with_x: true, rotation: ROT_B });
"""


def _pattern(canvas, rot_a=0, rot_b=0, grouped=True, extra='', cfg=''):
    """Arcs drawn for a 512x256 member with a 512x128 member under it."""
    setup = MIXED_PAIR_JS.replace('ROT_A', str(rot_a)).replace('ROT_B', str(rot_b))
    group = ("a.group_id = 'g1'; b.group_id = 'g1';"
             " const groups = [A.group([a, b])];") if grouped else " const groups = [];"
    return _js(canvas, setup + group + extra + """
    return A.withProject({ layers: [a, b], groups: groups%s }, () => A.arcs());
    """ % cfg)


def test_canvas_ok_an_ungrouped_pair_still_draws_a_pattern_each(canvas):
    """Baseline: 512x256 -> centre (256,128) r=0.4*256=102;
    512x128 at y=256 -> centre (256,320) r=0.4*128=51."""
    assert _pattern(canvas, grouped=False) == [
        {'x': 256, 'y': 128, 'r': 102},
        {'x': 256, 'y': 320, 'r': 51},
    ]


def test_canvas_ok_a_group_draws_one_pattern_sized_to_the_whole_wall(canvas):
    """Union 0,0 512x384 -> centre (256,192), r = 0.4 * 384 = 153.6."""
    assert _pattern(canvas) == [{'x': 256, 'y': 192, 'r': 154}]


def test_canvas_ok_hiding_a_section_shrinks_the_pattern_to_what_is_lit(canvas):
    """With the 64 px strip hidden the group has one drawn member, so the
    pattern is that member's own: centre (256,128), r 102."""
    assert _pattern(canvas, extra='b.visible = false;') == [
        {'x': 256, 'y': 128, 'r': 102}]


def test_canvas_ok_a_group_of_one_is_identical_to_the_lone_screen(canvas):
    """A group needs two drawn members before anything consolidates."""
    lone = _js(canvas, """
    const a = A.screen({ id: 1, name: 'A', columns: 4, rows: 2,
                         show_circle_with_x: true });
    return A.withProject({ layers: [a], groups: [] }, () => A.arcs());
    """)
    of_one = _js(canvas, """
    const a = A.screen({ id: 1, name: 'A', columns: 4, rows: 2,
                         show_circle_with_x: true });
    a.group_id = 'g1';
    return A.withProject({ layers: [a], groups: [A.group([a])] }, () => A.arcs());
    """)
    assert lone == of_one == [{'x': 256, 'y': 128, 'r': 102}]


def test_canvas_ok_a_member_on_another_canvas_keeps_its_own_pattern(canvas):
    """_groupDrawnMembers is scoped to one canvas, so neither member sees a
    peer and each draws its own - a union across two workspaces would be
    meaningless."""
    arcs = _js(canvas, """
    const a = A.screen({ id: 1, name: 'A', columns: 4, rows: 2,
                         show_circle_with_x: true });
    const b = A.screen({ id: 2, name: 'B', columns: 8, rows: 2,
                         cabinet_width: 64, cabinet_height: 64, offset_y: 256,
                         canvas_id: 'c2', show_circle_with_x: true });
    a.group_id = 'g1'; b.group_id = 'g1';
    return A.withProject({
        layers: [a, b], groups: [A.group([a, b])],
        canvases: [A.canvas('c1'), A.canvas('c2', { workspace_x: 10000 })],
    }, () => A.arcs());
    """)
    assert arcs == [{'x': 256, 'y': 128, 'r': 102},
                    {'x': 10256, 'y': 320, 'r': 51}]


def test_canvas_ok_show_look_offsets_cannot_move_the_pattern(canvas):
    """The pattern is Pixel Map only and Pixel Map is processor space, so a
    show offset of 3000 px must not move it by a pixel."""
    assert _pattern(canvas, extra='a.showOffsetX = 3000; b.showOffsetY = 4000;') == [
        {'x': 256, 'y': 192, 'r': 154}]


def test_canvas_ok_the_pattern_still_draws_in_export_mode(canvas):
    assert _pattern(canvas, cfg=', exportMode: true') == [
        {'x': 256, 'y': 192, 'r': 154}]


def test_canvas_ok_a_rotated_host_keeps_the_group_pattern_on_the_wall(canvas):
    """WAS A BUG, FIXED. The group's pattern used to be positioned from
    UNROTATED union bounds (_groupUnionBounds, via getLayerBoundsInActiveView)
    and then drawn INSIDE the host member's rotation transform, so the union was
    rotated about the HOST's centre rather than the wall's: with only the bottom
    strip rotated 180, the wall's centre (256,192) was thrown to (256,448) - 64
    px BELOW the bottom of a wall that ends at y=384.

    _groupUnionBounds now unions the members' DRAWN footprints, and both callers
    cancel the host's rotation first (_unrotateLayerInPlace), so the pattern
    spans the wall whatever any member's rotation. A 180 turn does not change a
    footprint, so the wall is still 512x384: centre (256,192), r = 0.4*384.
    """
    assert _pattern(canvas, rot_b=180) == [{'x': 256, 'y': 192, 'r': 154}]


def test_canvas_ok_a_wall_rotated_ninety_degrees_is_measured_where_it_draws(canvas):
    """WAS A BUG, FIXED - same cause, with the whole wall turned on its side.

    Both members carry rotation 90, each rotating about its OWN centre. The
    drawn footprints then span x 128..384, y -128..576, so the wall's real
    centre is (256, 224) and its short side is 256 px (r = 102).

    Before the fix: centre (384, 320) - the unrotated union centre (256,192)
    pushed through the host's 90 degree turn - and r = 154, sized from the
    unrotated short side.
    """
    assert _pattern(canvas, rot_a=90, rot_b=90) == [{'x': 256, 'y': 224, 'r': 102}]
    # ungrouped, each member's own pattern still lands on its own centre
    assert _pattern(canvas, rot_a=90, rot_b=90, grouped=False) == [
        {'x': 256, 'y': 128, 'r': 102},
        {'x': 256, 'y': 320, 'r': 51},
    ]


def test_canvas_ok_the_group_name_label_stays_on_the_wall(canvas):
    """WAS A BUG, FIXED - the same defect and the same fix: renderLayerLabels
    positions from _groupUnionBounds and now also cancels the host's rotation.

    The wall's name is centred on the wall (y = 192) whatever the host's
    rotation. Before the fix a host rotated 180 put it at y = 448, below a wall
    that ends at 384.
    """
    def label(rot_b):
        return _js(canvas, """
        const a = A.screen({ id: 1, name: 'A', columns: 4, rows: 2,
                             showLabelInfo: false });
        const b = A.screen({ id: 2, name: 'B', columns: 8, rows: 2,
                             cabinet_width: 64, cabinet_height: 64,
                             offset_y: 256, rotation: %d, showLabelInfo: false });
        a.group_id = 'g1'; b.group_id = 'g1';
        return A.withProject({ layers: [a, b], groups: [A.group([a, b])] },
            () => A.texts().filter(t => t.t === 'Main Wall'));
        """ % rot_b)
    assert label(0) == [{'t': 'Main Wall', 'x': 256, 'y': 192}]
    assert label(180) == [{'t': 'Main Wall', 'x': 256, 'y': 192}]


# ── cross-member port lines ───────────────────────────────────────────────

CROSS_PAIR_JS = """
    const a = A.screen(Object.assign({ id: 1, name: 'A', columns: 2, rows: 2,
        flowPattern: 'custom' }, A_OPTS));
    const b = A.screen(Object.assign({ id: 2, name: 'B', columns: 2, rows: 2,
        offset_x: 256, flowPattern: 'custom' }, B_OPTS));
    a.group_id = 'g1'; b.group_id = 'g1';
    a.customPortPaths = { 1: [
        { row: 0, col: 0 }, { row: 0, col: 1 },
        { row: 0, col: 0, layerId: 2 }, { row: 0, col: 1, layerId: 2 } ] };
"""


def _cable(canvas, a_opts='{}', b_opts='{}', cfg='', canvases='undefined',
           min_len=100):
    """The port-1 cable, as world-space segments, longest-first filtering out
    the arrowheads. Peer B has no paths of its own, so its automatic flow is
    excluded by only keeping segments that start on the owner's first cabinet
    chain - simplest reliable filter is the drawn order: the overlay pass runs
    last, so the final three long segments are the crossing cable."""
    setup = (CROSS_PAIR_JS.replace('A_OPTS', a_opts).replace('B_OPTS', b_opts))
    return _js(canvas, setup + """
    return A.withProject({ layers: [a, b], groups: [A.group([a, b])],
        canvases: %s, currentLayer: a, viewMode: 'data-flow'%s },
        () => A.overlayCable(%d));
    """ % (canvases, cfg, min_len))


def test_canvas_ok_a_crossing_cable_lands_on_every_cabinet_centre(canvas):
    """A r0c0 (64,64) -> A r0c1 (192,64) -> B r0c0 (320,64) -> B r0c1 (448,64)."""
    assert _cable(canvas) == [
        {'x1': 64, 'y1': 64, 'x2': 192, 'y2': 64},
        {'x1': 192, 'y1': 64, 'x2': 320, 'y2': 64},
        {'x1': 320, 'y1': 64, 'x2': 448, 'y2': 64},
    ]


def test_canvas_ok_each_member_contributes_its_OWN_show_look_offset(canvas):
    """B is dragged 444 px right for the show (offset_x 256 -> showOffsetX 700),
    so its cabinet centres move from 320/448 to 764/892. The owner's half must
    not move, the peer's half must."""
    assert _cable(canvas, b_opts='{ showOffsetX: 700 }') == [
        {'x1': 64, 'y1': 64, 'x2': 192, 'y2': 64},
        {'x1': 192, 'y1': 64, 'x2': 764, 'y2': 64},
        {'x1': 764, 'y1': 64, 'x2': 892, 'y2': 64},
    ]
    assert _cable(canvas, a_opts='{ showOffsetX: 1000 }') == [
        {'x1': 1064, 'y1': 64, 'x2': 1192, 'y2': 64},
        {'x1': 1192, 'y1': 64, 'x2': 320, 'y2': 64},
        {'x1': 320, 'y1': 64, 'x2': 448, 'y2': 64},
    ]


def test_canvas_ok_each_member_contributes_its_OWN_rotation(canvas):
    """Owner rotated 90 about its own centre (128,128):
    (64,64)->(192,64) and (192,64)->(192,192). The peer is untouched."""
    assert _cable(canvas, a_opts='{ rotation: 90 }') == [
        {'x1': 192, 'y1': 64, 'x2': 192, 'y2': 192},
        {'x1': 192, 'y1': 192, 'x2': 320, 'y2': 64},
        {'x1': 320, 'y1': 64, 'x2': 448, 'y2': 64},
    ]
    # peer rotated 270 about ITS centre (384,128): (320,64)->(320,192),
    # (448,64)->(320,64)
    assert _cable(canvas, b_opts='{ rotation: 270 }') == [
        {'x1': 64, 'y1': 64, 'x2': 192, 'y2': 64},
        {'x1': 192, 'y1': 64, 'x2': 320, 'y2': 192},
        {'x1': 320, 'y1': 192, 'x2': 320, 'y2': 64},
    ]
    # both 180: every cabinet centre mirrored through its own member's centre
    assert _cable(canvas, a_opts='{ rotation: 180 }', b_opts='{ rotation: 180 }') == [
        {'x1': 192, 'y1': 192, 'x2': 64, 'y2': 192},
        {'x1': 64, 'y1': 192, 'x2': 448, 'y2': 192},
        {'x1': 448, 'y1': 192, 'x2': 320, 'y2': 192},
    ]


def test_canvas_ok_a_crossing_cable_mirrors_correctly_in_back_perspective(canvas):
    """Canvas raster 1024 wide in Back view mirrors about x=1024, so every
    cabinet centre becomes 1024 - x: 960, 832, 704, 576."""
    canvases = ("[A.canvas('c1', { data_flow_perspective: 'back', "
                "raster_width: 1024, show_raster_width: 1024 })]")
    assert _cable(canvas, canvases=canvases) == [
        {'x1': 960, 'y1': 64, 'x2': 832, 'y2': 64},
        {'x1': 832, 'y1': 64, 'x2': 704, 'y2': 64},
        {'x1': 704, 'y1': 64, 'x2': 576, 'y2': 64},
    ]


def test_canvas_ok_a_crossing_cable_follows_the_canvas_workspace_offset(canvas):
    canvases = ("[A.canvas('c1', { workspace_x: 3000, workspace_y: 700, "
                "show_workspace_x: 3000, show_workspace_y: 700 })]")
    assert _cable(canvas, canvases=canvases) == [
        {'x1': 3064, 'y1': 764, 'x2': 3192, 'y2': 764},
        {'x1': 3192, 'y1': 764, 'x2': 3320, 'y2': 764},
        {'x1': 3320, 'y1': 764, 'x2': 3448, 'y2': 764},
    ]


def test_canvas_ok_a_crossing_cable_is_drawn_on_the_printed_map(canvas):
    """exportMode must NOT suppress it - a wall wired across two members has to
    appear on the print."""
    assert _cable(canvas, cfg=', exportMode: true') == [
        {'x1': 64, 'y1': 64, 'x2': 192, 'y2': 64},
        {'x1': 192, 'y1': 64, 'x2': 320, 'y2': 64},
        {'x1': 320, 'y1': 64, 'x2': 448, 'y2': 64},
    ]


def test_canvas_ok_a_crossing_cable_survives_both_zoom_extremes(canvas):
    """World geometry is zoom-invariant: at 8x every coordinate is 8x, at
    0.05x every coordinate is 0.05x, and nothing else changes."""
    assert _cable(canvas, cfg=', zoom: 8') == [
        {'x1': 512, 'y1': 512, 'x2': 1536, 'y2': 512},
        {'x1': 1536, 'y1': 512, 'x2': 2560, 'y2': 512},
        {'x1': 2560, 'y1': 512, 'x2': 3584, 'y2': 512},
    ]
    assert _cable(canvas, cfg=', zoom: 0.05') == [
        {'x1': 3, 'y1': 3, 'x2': 10, 'y2': 3},
        {'x1': 10, 'y1': 3, 'x2': 16, 'y2': 3},
        {'x1': 16, 'y1': 3, 'x2': 22, 'y2': 3},
    ]


def test_canvas_ok_a_peer_on_another_canvas_is_dropped_from_the_cable(canvas):
    """Not reachable, so the cable stops at the owner's own cabinets rather
    than jumping 5000 px across the workspace."""
    segs = _js(canvas, CROSS_PAIR_JS.replace('A_OPTS', '{}')
               .replace('B_OPTS', "{ canvas_id: 'c2' }") + """
    return A.withProject({ layers: [a, b], groups: [A.group([a, b])],
        canvases: [A.canvas('c1'), A.canvas('c2', { workspace_x: 5000 })],
        currentLayer: a, viewMode: 'data-flow' }, () => A.overlayCable(100));
    """)
    assert segs == [{'x1': 64, 'y1': 64, 'x2': 192, 'y2': 64}]


def test_canvas_ok_a_crossing_cable_stops_at_a_hidden_member(canvas):
    """WAS A BUG, FIXED. _renderCrossMemberPaths only checks the OWNER's
    visibility; getResolvedPathPanels deliberately keeps entries pointing at
    hidden members (app-power.js) so that hiding a member and showing it again
    does not destroy wiring already drawn onto it. The DRAWING side now drops
    them (_crossMemberDrawPanels), so the cable stops at the last cabinet that
    is actually drawn - the same way the circle-and-X shrinks to what is lit.

    Before the fix the printed map carried a data cable running off the wall
    into blank paper: three cable segments, and not one panel fill anywhere in
    the peer's half of the workspace.
    """
    result = _js(canvas, CROSS_PAIR_JS.replace('A_OPTS', '{}')
                 .replace('B_OPTS', '{ visible: false }') + """
    const cfg = { layers: [a, b], groups: [A.group([a, b])],
                  currentLayer: a, viewMode: 'data-flow' };
    const segs = A.withProject(cfg, () => A.overlayCable(100));
    const a2 = A.screen({ id: 1, name: 'A', columns: 2, rows: 2, flowPattern: 'custom' });
    const b2 = A.screen({ id: 2, name: 'B', columns: 2, rows: 2, offset_x: 256,
                          flowPattern: 'custom', visible: false });
    a2.group_id = 'g1'; b2.group_id = 'g1';
    a2.customPortPaths = a.customPortPaths;
    const peerFills = A.withProject({ layers: [a2, b2], groups: [A.group([a2, b2])],
        currentLayer: a2, viewMode: 'data-flow' },
        () => A.fills().filter(f => f.x >= 256 && f.w >= 100).length);
    return { segs: segs, peerFills: peerFills };
    """)
    # the cable ends on the owner's last drawn cabinet and goes no further
    assert result['segs'] == [{'x1': 64, 'y1': 64, 'x2': 192, 'y2': 64}]
    assert result['peerFills'] == 0    # and still nothing is drawn over there


# ── drag-select highlights: owner vs peer ─────────────────────────────────

SEL_PAIR_JS = """
    const a = A.screen(Object.assign({ id: 1, name: 'A', columns: 2, rows: 2,
        flowPattern: 'custom' }, A_OPTS));
    const b = A.screen(Object.assign({ id: 2, name: 'B', columns: 2, rows: 2,
        offset_x: 256, flowPattern: 'custom' }, B_OPTS));
    a.group_id = 'g1'; b.group_id = 'g1';
"""


def _sel(canvas, a_opts='{}', b_opts='{}'):
    """The two drag-select highlight rects (owner's R0C0, peer's R0C0)."""
    setup = SEL_PAIR_JS.replace('A_OPTS', a_opts).replace('B_OPTS', b_opts)
    return _js(canvas, setup + """
    return A.withProject({ layers: [a, b], groups: [A.group([a, b])],
        currentLayer: a, viewMode: 'data-flow',
        customSelection: ['1:0,0', '2:0,0'] },
        () => A.fills().filter(f => f.style === 'rgba(0, 0, 0, 0.6)')
                       .filter(f => f.w === 128 && f.h === 128)
                       .map(f => [f.x, f.y]));
    """)


def test_canvas_ok_owner_and_peer_highlights_land_on_their_own_cabinets(canvas):
    assert _sel(canvas) == [[0, 0], [256, 0]]


def test_canvas_ok_a_peers_own_show_look_offset_moves_only_its_highlight(canvas):
    assert _sel(canvas, b_opts='{ showOffsetX: 700 }') == [[0, 0], [700, 0]]
    assert _sel(canvas, a_opts='{ showOffsetX: 700 }') == [[700, 0], [256, 0]]


def test_canvas_ok_a_rotated_owners_highlight_follows_its_own_rotation(canvas):
    """WAS A BUG, FIXED. The peer's highlight went through
    _crossMemberPanelShim, which bakes in that member's rotation; the owner's
    went through _withOverlayLayerTransform, which applies the workspace
    translate, the mirror and the Show Look offset but NOT the layer's rotation.
    So on a rotated wall the peer's highlight moved and the owner's did not.

    Both halves now draw in the one cross-member frame with each cabinet's own
    rotation baked into its rect, so both members move together.

    Before the fix: mid drag-select across a rotated wall, half the highlighted
    cabinets were the ones you were pointing at and half were one cabinet away,
    so the operator wired the wrong cabinet into the port.
    """
    # rotation 90: owner R0C0 draws at 128,0 and the highlight is there
    assert _sel(canvas, a_opts='{ rotation: 90 }', b_opts='{ rotation: 90 }') == [
        [128, 0], [384, 0]]
    # rotation 180: owner R0C0 draws at 128,128
    assert _sel(canvas, a_opts='{ rotation: 180 }', b_opts='{ rotation: 180 }') == [
        [128, 128], [384, 128]]


# ── continuous cabinet numbering across a group ───────────────────────────

WALL_JS = """
    const a = A.screen({ id: 1, name: 'A', columns: 4, rows: 2, show_numbers: true,
                         cabinetIdStyle: STYLE, visible: A_VIS });
    const b = A.screen({ id: 2, name: 'B', columns: 8, rows: 2,
                         cabinet_width: 64, cabinet_height: 64, offset_y: 256,
                         show_numbers: true, cabinetIdStyle: STYLE, visible: B_VIS });
    a.group_id = 'g1'; b.group_id = 'g1';
"""


def _ids(canvas, style="'sequential'", a_vis='true', b_vis='true', grouped=True):
    setup = (WALL_JS.replace('STYLE', style)
             .replace('A_VIS', a_vis).replace('B_VIS', b_vis))
    groups = "[A.group([a, b])]" if grouped else "[]"
    return _js(canvas, setup + """
    return A.withProject({ layers: [a, b], groups: %s, viewMode: 'cabinet-id' },
        () => A.texts().filter(t => /^[A-Z]*[0-9]+$/.test(t.t)).map(t => t.t));
    """ % groups)


def test_canvas_ok_numbers_run_straight_through_a_mixed_size_wall(canvas):
    """8 cabinets of 128 px over 16 of 64 px: 1..24, each exactly once, no
    gaps, in reading order down the wall."""
    ids = _ids(canvas)
    assert ids == [str(n) for n in range(1, 9)] + [str(n) for n in range(9, 25)]
    assert len(ids) == len(set(ids)) == 24


def test_canvas_ok_the_same_wall_ungrouped_still_restarts_at_one(canvas):
    ids = _ids(canvas, grouped=False)
    assert ids == [str(n) for n in range(1, 9)] + [str(n) for n in range(1, 17)]


def test_canvas_ok_a_grid_style_labels_every_cabinet_of_the_wall_uniquely(canvas):
    """Positions are ranked on the wall, so the 128 px member's letters skip
    (A, C, E, G) where the 64 px member fills B, D, F, H. Every label distinct."""
    ids = _ids(canvas, style="'column-row'")
    assert ids[:8] == ['A1', 'C1', 'E1', 'G1', 'A2', 'C2', 'E2', 'G2']
    assert ids[8:16] == ['A3', 'B3', 'C3', 'D3', 'E3', 'F3', 'G3', 'H3']
    assert ids[16:] == ['A4', 'B4', 'C4', 'D4', 'E4', 'F4', 'G4', 'H4']
    assert len(ids) == len(set(ids)) == 24


def test_canvas_ok_overlapping_members_fall_back_to_sequential_numbers(canvas):
    """Two members sharing slot origins cannot be labelled uniquely by grid, so
    the whole group drops to the wall's sequential numbers rather than drawing
    two A1s."""
    ids = _js(canvas, """
    const a = A.screen({ id: 1, name: 'A', columns: 2, rows: 2, show_numbers: true,
                         cabinetIdStyle: 'column-row' });
    const b = A.screen({ id: 2, name: 'B', columns: 2, rows: 2, show_numbers: true,
                         cabinetIdStyle: 'column-row' });
    a.group_id = 'g1'; b.group_id = 'g1';
    return A.withProject({ layers: [a, b], groups: [A.group([a, b])],
        viewMode: 'cabinet-id' },
        () => A.texts().filter(t => /^[0-9]+$/.test(t.t)).map(t => t.t));
    """)
    assert sorted(ids, key=int) == [str(n) for n in range(1, 9)]
    assert len(ids) == len(set(ids))


def test_canvas_bug_hiding_the_top_section_leaves_the_wall_numbered_from_nine(canvas):
    """CONFIRMED, and DELIBERATE per canvas.js:5334-5342 - hiding a member must
    not renumber another. The crew-facing consequence is worth stating: with
    the top half hidden, the wall on the drawing is labelled 9..16 and nothing
    is labelled 1..8.
    """
    ids = _js(canvas, """
    const a = A.screen({ id: 1, name: 'A', columns: 4, rows: 2, offset_y: 256,
                         show_numbers: true, cabinetIdStyle: 'sequential' });
    const b = A.screen({ id: 2, name: 'B', columns: 4, rows: 2,
                         show_numbers: true, cabinetIdStyle: 'sequential',
                         visible: false });
    a.group_id = 'g1'; b.group_id = 'g1';
    return A.withProject({ layers: [a, b], groups: [A.group([a, b])],
        viewMode: 'cabinet-id' },
        () => A.texts().filter(t => /^[0-9]+$/.test(t.t)).map(t => t.t));
    """)
    assert ids == [str(n) for n in range(9, 17)]


def test_canvas_ok_a_rotated_member_numbers_by_where_it_draws(canvas):
    """WAS A BUG, FIXED - and the "known limit" comment it was documented under
    is gone with it. getPositionLattice now ranks every cabinet's slot origin
    through that member's own draw frame, so the top member turned 90 degrees is
    numbered in the order somebody walking the wall reads it.

    The rotated member's grid axes trade places: its ROWS now run along the
    wall's x, so its two rows occupy lattice columns at x=128 and x=256 and its
    four columns occupy lattice rows at y=-128, 0, 128, 256. Reading order down
    the wall then starts at the drawn top-left cabinet, which is the rotated
    member's R1C0 at drawn centre (192,-64), not its R0C0.

    The second member is untouched: it is unrotated, and 13 is still the fifth
    cabinet of its top row at (288,288).
    """
    positions = _js(canvas, """
    const a = A.screen({ id: 1, name: 'A', columns: 4, rows: 2, show_numbers: true,
                         cabinetIdStyle: 'sequential', rotation: 90 });
    const b = A.screen({ id: 2, name: 'B', columns: 8, rows: 2,
                         cabinet_width: 64, cabinet_height: 64, offset_y: 256,
                         show_numbers: true, cabinetIdStyle: 'sequential' });
    a.group_id = 'g1'; b.group_id = 'g1';
    return A.withProject({ layers: [a, b], groups: [A.group([a, b])],
        viewMode: 'cabinet-id' },
        () => A.texts().filter(t => /^[0-9]+$/.test(t.t))
                       .map(t => [t.t, t.x, t.y]));
    """)
    by_id = {t: (x, y) for t, x, y in positions}
    # "1" is the DRAWN top-left cabinet of the rotated member, "2" beside it
    assert by_id['1'] == (192, -64)
    assert by_id['2'] == (320, -64)
    # the next lattice row down, left to right again
    assert by_id['3'] == (192, 64)
    assert by_id['4'] == (320, 64)
    # the unrotated member is numbered exactly as before
    assert by_id['13'] == (288, 288)
    assert len(by_id) == 24 == len(positions)
