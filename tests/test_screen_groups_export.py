"""Screen groups (v0.10.9) - exporting a group as ONE screen.

A wall built from 1m JP5 cabinets AND 0.5m standard cabinets has to be two
layers, because the grid is uniform per layer. A group makes them behave as
one screen, and an export is where that has to become visible to somebody
OUTSIDE the app: Resolume must map one shape, Photoshop must show one layer,
and both must carry the GROUP's name, once.

The shape rule is the owner's: "only look at the shape of the layer, if a
rectangle/square then just use its x,y and resolution. if polygon then it is a
polygon... polygon uses x,y and shape but only where panels are." So a group
whose members happen to tile into a plain rectangle exports as a plain
rectangle, not as a polygon with a seam down the middle.

Expected contours are derived from actual ``_build_panels`` output wherever
they are not literal, the same way tests/test_export_contour.py does it.

``test_ungrouped_*`` is the load-bearing test in this file: mappings already
in the field must re-export unmoved.
"""

import hashlib
import io
import random
import zipfile

import pytest

import app as app_module
from app import (
    _build_panels,
    _compute_layers_contour,
    _compute_panel_contour,
    _export_unit_bounds,
    _export_unit_needs_polygon,
    _export_units,
    _layer_bounds,
    _resolume_polygon,
    _resolume_slice,
    generate_resolume_xml,
    render_layer_to_image,
    render_unit_to_image,
)


# ── helpers ───────────────────────────────────────────────────────────────

def _screen(lid, name, rows, cols, cw=128, ch=128, off_x=0, off_y=0,
            states=None, canvas_id=None, visible=True):
    """A screen layer with real panel geometry from _build_panels."""
    layer = {
        'id': lid, 'name': name, 'type': 'screen', 'visible': visible,
        'rows': rows, 'columns': cols,
        'cabinet_width': cw, 'cabinet_height': ch,
        'offset_x': off_x, 'offset_y': off_y,
        'canvas_id': canvas_id,
    }
    layer['panels'] = _build_panels(layer, dict(states or {}))
    return layer


def _project(layers, groups=None, canvases=None, raster=(1920, 1080)):
    project = {
        'name': 'Proj',
        'layers': layers,
        'raster_width': raster[0], 'raster_height': raster[1],
    }
    if groups is not None:
        project['groups'] = groups
    if canvases is not None:
        project['canvases'] = canvases
    return project


def _group(gid, name, layers):
    """Make a group over these layers and stamp group_id on both sides."""
    for layer in layers:
        layer['group_id'] = gid
    return {'id': gid, 'name': name, 'layer_ids': [l['id'] for l in layers]}


def _xml(project):
    """Resolume XML with a fixed RNG so uniqueIds are reproducible."""
    random.seed(1234)
    return generate_resolume_xml(
        project, 'Proj', project['raster_width'], project['raster_height'])


def _shape_names(xml):
    """(tag, name) for every Slice/Polygon in the XML, in document order."""
    import re
    out = []
    for m in re.finditer(r'<(Slice|Polygon) uniqueId=[^>]*>\s*'
                         r'<Params name="Common">\s*'
                         r'<Param name="Name" T="STRING" default="Layer" value="([^"]*)"',
                         xml):
        out.append((m.group(1), m.group(2)))
    return out


def _contour_points(xml):
    """Every <points> block's vertices, per shape, in document order."""
    import re
    blocks = re.findall(r'<InputContour closed="1">\s*<points>(.*?)</points>',
                        xml, re.S)
    return [
        [(int(x), int(y)) for x, y in re.findall(r'<v x="(-?\d+)" y="(-?\d+)"/>', b)]
        for b in blocks
    ]


def _output_rects(xml):
    """The OutputRect of every shape, as (x1, y1, x2, y2)."""
    import re
    out = []
    for block in re.findall(r'<OutputRect orientation="0">(.*?)</OutputRect>',
                            xml, re.S):
        pts = [(float(x), float(y))
               for x, y in re.findall(r'<v x="(-?[\d.]+)" y="(-?[\d.]+)"/>', block)]
        out.append((pts[0][0], pts[0][1], pts[2][0], pts[2][1]))
    return out


def _assert_axis_aligned_loop(contour):
    """Every segment (including the closing one) is horizontal or vertical and
    turns at each vertex - lifted from tests/test_export_contour.py."""
    assert len(contour) >= 4, contour
    n = len(contour)
    for i in range(n):
        x1, y1 = contour[i]
        x2, y2 = contour[(i + 1) % n]
        assert (x1 == x2) != (y1 == y2), f'segment {i} not axis-aligned'
    assert len(set(contour)) == n, f'repeated vertex in {contour}'


# ── the load-bearing test: ungrouped exports must not move ────────────────

# Captured from generate_resolume_xml BEFORE groups touched the export path,
# with random.seed(1234) so the uniqueIds are reproducible. Every one of these
# projects is UNGROUPED, and every one of them is a mapping shape a user may
# already have wired into a Resolume composition. If one of these hashes
# changes, an existing show moved.
#
# To re-pin deliberately (i.e. the XML template itself changed on purpose),
# print `_xml(project)` for the failing case and diff it against the file the
# user has - never just paste the new hash in.
def _ungrouped_cases():
    return {
        'single_plain': _project([_screen(1, 'Main', 3, 4)]),
        'two_walls': _project([
            _screen(1, 'Left', 3, 4),
            _screen(2, 'Right', 2, 2, off_x=700),
        ]),
        'hidden_polygon': _project([
            _screen(1, 'L Wall', 3, 4, states={(2, 3): {'hidden': True}}),
        ]),
        'multi_canvas': _project(
            [
                _screen(1, 'A', 3, 4, canvas_id='c1'),
                _screen(2, 'B', 2, 2, canvas_id='c2',
                        states={(0, 0): {'blank': True}}),
            ],
            canvases=[
                {'id': 'c1', 'name': 'Canvas 1', 'workspace_x': 0,
                 'workspace_y': 0, 'raster_width': 1920, 'raster_height': 1080,
                 'visible': True},
                {'id': 'c2', 'name': 'Canvas 2', 'workspace_x': 2000,
                 'workspace_y': 0, 'raster_width': 1280, 'raster_height': 720,
                 'visible': True},
            ],
        ),
        'mixed_sizes': _project([
            _screen(1, 'JP5', 2, 2, cw=128, ch=128),
            _screen(2, 'Std', 4, 4, cw=64, ch=64, off_x=256),
        ]),
        'half_and_blank': _project([
            _screen(1, 'Odd', 3, 3, states={
                (2, 0): {'halfTile': 'height'}, (0, 2): {'blank': True}}),
        ]),
    }


PINNED_UNGROUPED_XML = {
    'single_plain': '025b78b4c072aaf3581d12da9b0e50deedf19bb7e5ccd01d6f1d4192fedb3730',
    'two_walls': '730dbe2344024c2c3846e11b1d828b826a9f74b9c2d949b7e79171c3d7e9bd64',
    'hidden_polygon': '106e2a89354cbe1520c11c280b4db41847d48ef0a111dc6902ddc28d81b7d485',
    'multi_canvas': 'b4355349349e5bef1292d245c961d399254f1e4a8c959e203b353f5f618cb84f',
    'mixed_sizes': '2e1c537267a99cfc6bfbfb597eb36544dc52d51002aad8a67c407f51b565318b',
    'half_and_blank': '27935b59aa19b9e1da842d93137594f43696a350cd12300ca2e27fa88fdee02e',
}


@pytest.mark.parametrize('case', sorted(PINNED_UNGROUPED_XML))
def test_ungrouped_resolume_xml_is_byte_identical(case):
    """An ungrouped project exports the exact bytes it did before groups."""
    xml = _xml(_ungrouped_cases()[case])
    assert hashlib.sha256(xml.encode('utf-8')).hexdigest() == PINNED_UNGROUPED_XML[case]


def test_ungrouped_project_still_emits_one_shape_per_layer():
    """The readable half of the pin: names, count and order are unchanged."""
    xml = _xml(_ungrouped_cases()['two_walls'])
    assert _shape_names(xml) == [('Slice', 'Left'), ('Slice', 'Right')]


def test_ungrouped_shape_helpers_ignore_the_new_arguments():
    """_resolume_slice/_resolume_polygon grew members/name arguments; passing
    the one-layer values must produce the same string as omitting them."""
    plain = _screen(1, 'Main', 3, 4)
    notched = _screen(2, 'L Wall', 3, 4, states={(2, 3): {'hidden': True}})
    assert (_resolume_slice(plain, 7) ==
            _resolume_slice(plain, 7, [plain], plain['name']))
    assert (_resolume_polygon(notched, 7) ==
            _resolume_polygon(notched, 7, [notched], notched['name']))


def test_ungrouped_helpers_reduce_to_the_single_layer_ones():
    """The unit helpers are the old per-layer helpers when the unit is one
    layer - which is why the ungrouped path cannot drift."""
    layer = _screen(1, 'Odd', 3, 3, states={(2, 0): {'halfTile': 'height'}})
    assert _compute_layers_contour([layer]) == _compute_panel_contour(layer)
    assert _export_unit_bounds([layer]) == _layer_bounds(layer)
    # And the no-panels fallback to rows/columns * cabinet size survives.
    bare = {'rows': 2, 'columns': 3, 'cabinet_width': 128, 'cabinet_height': 128,
            'offset_x': 10, 'offset_y': 20}
    assert _export_unit_bounds([bare]) == _layer_bounds(bare)


def test_ungrouped_project_units_are_one_per_layer():
    layers = [_screen(1, 'A', 1, 1), _screen(2, 'B', 1, 1, off_x=200)]
    assert _export_units(_project(layers), layers) == [('A', [layers[0]]),
                                                       ('B', [layers[1]])]
    # A project with no 'groups' key at all (pre-v0.10.9 file) behaves the same.
    assert _export_units({'layers': layers}, layers) == [('A', [layers[0]]),
                                                         ('B', [layers[1]])]


# ── a group that tiles into a rectangle is a rectangle ────────────────────

def _rectangular_group():
    """1m JP5 cabinets (128px) beside 0.5m standard cabinets (64px), tiling
    into a plain 384 x 256 rectangle. The real reason groups exist."""
    jp5 = _screen(1, 'JP5 block', 2, 2, cw=128, ch=128)
    std = _screen(2, 'Std block', 4, 2, cw=64, ch=64, off_x=256)
    group = _group('g1', 'Main Wall', [jp5, std])
    return _project([jp5, std], groups=[group]), jp5, std


def test_grouped_rectangle_is_one_contour_with_four_corners():
    project, jp5, std = _rectangular_group()
    # The two members really are different cabinet sizes and really do abut.
    assert jp5['panels'][0]['width'] == 128 and std['panels'][0]['width'] == 64
    assert _layer_bounds(jp5)['width'] == 256
    assert _layer_bounds(std)['x'] == 256

    contour = _compute_layers_contour([jp5, std])
    assert contour == [(384, 0), (0, 0), (0, 256), (384, 256)]
    _assert_axis_aligned_loop(contour)
    # Not two shapes stacked: neither member alone reaches the right edge.
    assert _compute_panel_contour(jp5) != contour
    assert _compute_panel_contour(std) != contour


def test_grouped_rectangle_exports_one_slice_named_for_the_group():
    project, _jp5, _std = _rectangular_group()
    xml = _xml(project)
    assert _shape_names(xml) == [('Slice', 'Main Wall')]
    assert 'JP5 block' not in xml and 'Std block' not in xml
    # x, y and resolution of the union - the whole 384 x 256 wall.
    assert _output_rects(xml) == [(0.0, 0.0, 384.0, 256.0)]
    assert '<Polygon' not in xml


def test_grouped_rectangle_is_not_a_polygon():
    _project_, jp5, std = _rectangular_group()
    assert _export_unit_needs_polygon([jp5, std]) is False


# ── a group that tiles into an L is a polygon ─────────────────────────────

def _l_shaped_group():
    """1m block 256 wide x 256 tall, with a 0.5m block only 128 tall beside
    it: an L, even though neither member has a hidden panel."""
    jp5 = _screen(1, 'JP5 block', 2, 2, cw=128, ch=128)
    std = _screen(2, 'Std block', 2, 2, cw=64, ch=64, off_x=256)
    group = _group('g1', 'L Wall', [jp5, std])
    return _project([jp5, std], groups=[group]), jp5, std


def test_grouped_l_shape_is_one_polygon_following_the_panels():
    _p, jp5, std = _l_shaped_group()
    assert _layer_bounds(std)['height'] == 128   # short member
    contour = _compute_layers_contour([jp5, std])
    assert contour == [
        (384, 0),      # top-right of the short member
        (0, 0),        # left along the top
        (0, 256),      # down the tall member's left side
        (256, 256),    # right along the bottom - only where panels are
        (256, 128),    # up the step to the short member
        (384, 128),    # out to its bottom-right
    ]
    _assert_axis_aligned_loop(contour)
    assert _export_unit_needs_polygon([jp5, std]) is True


def test_grouped_l_shape_exports_one_polygon_named_for_the_group():
    project, _jp5, _std = _l_shaped_group()
    xml = _xml(project)
    assert _shape_names(xml) == [('Polygon', 'L Wall')]
    assert _contour_points(xml) == [[
        (384, 0), (0, 0), (0, 256), (256, 256), (256, 128), (384, 128),
    ]]
    # The bounding box is still the union - the polygon lives inside it.
    assert _output_rects(xml) == [(0.0, 0.0, 384.0, 256.0)]


# ── hidden / blank cabinets at a group edge ───────────────────────────────

def _rect_group_with_state(state):
    """The rectangular 1m + 0.5m wall with one 0.5m cabinet at the outer
    bottom-right corner knocked out."""
    jp5 = _screen(1, 'JP5 block', 2, 2, cw=128, ch=128)
    std = _screen(2, 'Std block', 4, 2, cw=64, ch=64, off_x=256,
                  states={(3, 1): dict(state)})
    return _project([jp5, std], groups=[_group('g1', 'Main Wall', [jp5, std])]), jp5, std


def test_group_traces_around_a_hidden_edge_cabinet():
    project, jp5, std = _rect_group_with_state({'hidden': True})
    contour = _compute_layers_contour([jp5, std])
    assert contour == [
        (384, 0), (0, 0), (0, 256), (320, 256), (320, 192), (384, 192),
    ]
    _assert_axis_aligned_loop(contour)
    xml = _xml(project)
    assert _shape_names(xml) == [('Polygon', 'Main Wall')]
    assert _contour_points(xml) == [contour]


def test_group_traces_around_a_blank_edge_cabinet():
    """Blank is not lit surface either, so it must trace the same as hidden."""
    _p1, jp5_b, std_b = _rect_group_with_state({'blank': True})
    _p2, jp5_h, std_h = _rect_group_with_state({'hidden': True})
    assert (_compute_layers_contour([jp5_b, std_b]) ==
            _compute_layers_contour([jp5_h, std_h]))


def test_group_with_a_knocked_out_cabinet_is_smaller_than_the_full_wall():
    _p, jp5, std = _rect_group_with_state({'hidden': True})
    full, _j, _s = _rectangular_group()
    full_members = full['layers']
    assert (_compute_layers_contour([jp5, std]) !=
            _compute_layers_contour(full_members))


# ── mixed cabinet sizes, a realistic 1m + 0.5m wall ───────────────────────

def test_realistic_mixed_size_wall_unions_correctly():
    """A 3m x 2m wall: four 1m JP5 cabinets on the left, a 1m-wide block of
    eight 0.5m standard cabinets on the right. 128px per metre throughout.

    Every expectation is read back off the panels _build_panels produced, so
    this cannot bake in the arithmetic it is meant to check.
    """
    jp5 = _screen(1, 'JP5', 2, 2, cw=128, ch=128)              # 2m x 2m
    std = _screen(2, 'Std', 4, 2, cw=64, ch=64, off_x=256)     # 1m x 2m
    members = [jp5, std]

    # The two grids are genuinely different and genuinely adjacent.
    assert {p['width'] for p in jp5['panels']} == {128}
    assert {p['width'] for p in std['panels']} == {64}
    assert max(p['x'] + p['width'] for p in jp5['panels']) == \
        min(p['x'] for p in std['panels'])

    bounds = _export_unit_bounds(members)
    assert (bounds['x'], bounds['y']) == (0, 0)
    assert (bounds['width'], bounds['height']) == (384, 256)   # 3m x 2m

    contour = _compute_layers_contour(members)
    # No seam: the shared edge at x=256 produces no vertex.
    assert contour == [(384, 0), (0, 0), (0, 256), (384, 256)]
    assert all(pt[0] != 256 for pt in contour)


def test_mixed_size_wall_with_a_half_tile_row_keeps_the_real_height():
    """Half tiles inside a member still collapse the row, and the group's
    contour follows the real geometry rather than the nominal grid."""
    jp5 = _screen(1, 'JP5', 2, 2, cw=128, ch=128)
    std = _screen(2, 'Std', 4, 2, cw=64, ch=64, off_x=256,
                  states={(3, c): {'halfTile': 'height'} for c in range(2)})
    short = next(p for p in std['panels'] if p['row'] == 3 and p['col'] == 0)
    assert short['height'] == 32 and short['y'] + short['height'] == 224

    contour = _compute_layers_contour([jp5, std])
    assert contour == [
        (384, 0), (0, 0), (0, 256), (256, 256), (256, 224), (384, 224),
    ]
    _assert_axis_aligned_loop(contour)


# ── degenerate groups ─────────────────────────────────────────────────────

def test_group_of_one_behaves_like_a_lone_layer():
    """_create_group refuses a single member, but a hand-edited project file
    can still carry one. It must export exactly as the bare layer does."""
    only = _screen(1, 'Solo', 3, 4)
    project = _project([only], groups=[_group('g1', 'Solo Group', [only])])
    assert _export_units(project, [only]) == [('Solo Group', [only])]
    assert _compute_layers_contour([only]) == _compute_panel_contour(only)
    assert _export_unit_bounds([only]) == _layer_bounds(only)
    assert _export_unit_needs_polygon([only]) is False   # the lone-layer rule

    xml = _xml(project)
    # Same shape as ungrouped, only the name comes from the group.
    assert _shape_names(xml) == [('Slice', 'Solo Group')]
    assert _output_rects(xml) == [(0.0, 0.0, 512.0, 384.0)]


def test_group_members_in_different_canvases_do_not_crash():
    """A member scoped to another canvas exports with THAT canvas - the same
    rule the Resolume screen loop already applies to layers."""
    a = _screen(1, 'A', 2, 2, canvas_id='c1')
    b = _screen(2, 'B', 2, 2, canvas_id='c2')
    project = _project(
        [a, b], groups=[_group('g1', 'Split Wall', [a, b])],
        canvases=[
            {'id': 'c1', 'name': 'Canvas 1', 'workspace_x': 0, 'workspace_y': 0,
             'raster_width': 1920, 'raster_height': 1080, 'visible': True},
            {'id': 'c2', 'name': 'Canvas 2', 'workspace_x': 2000,
             'workspace_y': 0, 'raster_width': 1280, 'raster_height': 720,
             'visible': True},
        ],
    )
    xml = _xml(project)
    # One shape per canvas, each named for the group, neither spanning both.
    assert _shape_names(xml) == [('Slice', 'Split Wall'), ('Slice', 'Split Wall')]
    assert _output_rects(xml) == [(0.0, 0.0, 256.0, 256.0)] * 2


def test_group_with_every_member_hidden_does_not_crash():
    """All panels hidden: no contour to trace, but the export must still
    produce a document rather than raising."""
    states = {(r, c): {'hidden': True} for r in range(2) for c in range(2)}
    a = _screen(1, 'A', 2, 2, states=states)
    b = _screen(2, 'B', 2, 2, off_x=256, states=states)
    project = _project([a, b], groups=[_group('g1', 'Dark Wall', [a, b])])

    assert _compute_layers_contour([a, b]) == []
    xml = _xml(project)
    assert _shape_names(xml) == [('Polygon', 'Dark Wall')]
    assert _contour_points(xml) == [[]]
    assert xml.startswith('<?xml version="1.0" encoding="utf-8"?>')


def test_group_id_naming_a_missing_group_falls_back_to_the_layer():
    """A stale group_id (the group was deleted) must not swallow the layer."""
    a = _screen(1, 'A', 2, 2)
    a['group_id'] = 'g99'
    project = _project([a], groups=[])
    assert _export_units(project, [a]) == [('A', [a])]
    assert _shape_names(_xml(project)) == [('Slice', 'A')]


def test_empty_unit_bounds_and_image_are_safe():
    assert _export_unit_bounds([]) == {'x': 0, 'y': 0, 'width': 0, 'height': 0}
    img = render_unit_to_image([], 64, 32)
    assert img.size == (64, 32)
    assert img.getpixel((0, 0)) == (0, 0, 0, 0)


# ── PNG / PSD: the group renders into one region ──────────────────────────

def test_render_unit_composites_every_member():
    """A group's members land in ONE image, so an outside viewer sees one
    screen. A single member returns exactly the per-layer render."""
    jp5 = _screen(1, 'JP5', 2, 2, cw=128, ch=128)
    std = _screen(2, 'Std', 4, 2, cw=64, ch=64, off_x=256)

    solo = render_layer_to_image(jp5, 512, 512)
    assert render_unit_to_image([jp5], 512, 512).tobytes() == solo.tobytes()

    unit = render_unit_to_image([jp5, std], 512, 512)
    # Opaque across the whole union, transparent outside it.
    assert unit.getpixel((10, 10))[3] == 255      # JP5 member
    assert unit.getpixel((300, 10))[3] == 255     # standard member
    assert unit.getpixel((300, 300))[3] == 0      # below both
    assert unit.getpixel((400, 10))[3] == 0       # right of both


def test_psd_export_gives_a_group_one_named_layer(client):
    """/api/export/psd names a grouped wall once, for the group.

    Runs in both worlds without skipping: with pytoshop installed the route
    returns a PSD (layer names are plain bytes inside it), without it the
    route falls back to a ZIP of per-unit PNGs.
    """
    jp5 = _screen(1, 'JP5 block', 2, 2, cw=128, ch=128)
    std = _screen(2, 'Std block', 4, 2, cw=64, ch=64, off_x=256)
    app_module.current_project = _project(
        [jp5, std], groups=[_group('g1', 'Main Wall', [jp5, std])],
        raster=(512, 512))

    resp = client.post('/api/export/psd', json={})
    assert resp.status_code == 200
    body = resp.data

    if body[:4] == b'8BPS':
        assert b'Main Wall' in body
        assert b'JP5 block' not in body and b'Std block' not in body
    else:
        assert body[:2] == b'PK'
        names = zipfile.ZipFile(io.BytesIO(body)).namelist()
        assert sorted(names) == ['Main Wall.png', 'manifest.json']


def test_psd_export_still_names_ungrouped_layers_individually(client):
    """The same route, no groups: one entry per layer, as before."""
    a = _screen(1, 'Left', 2, 2)
    b = _screen(2, 'Right', 2, 2, off_x=300)
    app_module.current_project = _project([a, b], raster=(512, 512))

    resp = client.post('/api/export/psd', json={})
    assert resp.status_code == 200
    body = resp.data
    if body[:4] == b'8BPS':
        assert b'Left' in body and b'Right' in body
    else:
        names = zipfile.ZipFile(io.BytesIO(body)).namelist()
        assert sorted(names) == ['Left.png', 'Right.png', 'manifest.json']
