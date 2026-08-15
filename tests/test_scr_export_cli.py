"""The canvas -> section mapping in src/scr_project.py.

Why this exists
---------------
The binary layer is covered by test_scr_roundtrip.py, which re-encodes real
show files and diffs the bytes. That says nothing about the layer above it -
which cabinets go in which section, on which sending card - and the previous
attempt at SCR export got exactly that part wrong: it emitted one section per
screen LAYER, and two layers only ever ended up in one section by coincidence.

So these tests are about the MODEL. One canvas is one section on one sending
card; the screen layers on a canvas are cabinets inside that one section.

The projects here are built inline. Nothing reads the running server or the
user's show files: those are production drawings, they are not in the repo, and
a test that needs them is a test that silently stops running.
"""

import collections
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

from scr_decoder import decode_scr  # noqa: E402
from scr_encoder import build_multi_screen_scr  # noqa: E402
from scr_project import Warnings, build_sections, verify  # noqa: E402


# ── building projects ────────────────────────────────────────────────────

def _layer(layer_id, canvas_id, cols, rows, cw=100, ch=100, ox=0, oy=0,
           hidden=(), blank=(), name=None, relative=False, **extra):
    """A screen layer with a full cols x rows grid of cabinets.

    Panel x/y carry the layer offset, which is what the server writes - the
    app's own geometry maths depends on it. `relative=True` leaves it out to
    exercise the other reading.
    """
    panels = []
    for row in range(rows):
        for col in range(cols):
            panels.append({
                'col': col, 'row': row,
                'x': (0 if relative else ox) + col * cw,
                'y': (0 if relative else oy) + row * ch,
                'width': cw, 'height': ch,
                'hidden': (col, row) in hidden,
                'blank': (col, row) in blank,
                'number': row * cols + col + 1,
            })
    layer = {
        'id': layer_id, 'canvas_id': canvas_id, 'type': 'screen',
        'name': name or 'Layer %s' % layer_id,
        'columns': cols, 'rows': rows,
        'cabinet_width': cw, 'cabinet_height': ch,
        'offset_x': ox, 'offset_y': oy,
        'flowPattern': 'tl-h', 'portMappingMode': 'organized',
        'processorType': 'novastar-armor', 'bitDepth': 8, 'frameRate': 60,
        'panels': panels,
    }
    layer.update(extra)
    return layer


def _project(canvases, layers):
    return {
        'name': 'Test', 'canvases': canvases, 'layers': layers,
        'raster_width': 3840, 'raster_height': 2160,
    }


def _canvas(canvas_id, name):
    return {'id': canvas_id, 'name': name,
            'raster_width': 3840, 'raster_height': 2160}


def _sections(project):
    return build_sections(project, Warnings())


def _cell(section, col, row):
    for panel in section['panels']:
        if panel['col'] == col and panel['row'] == row:
            return panel
    raise AssertionError('no cell (%d,%d) in the section' % (col, row))


def _is_terminator_cell(section, col, row):
    """The record at binary (cols-1, rows-1) is a terminator, not a cabinet.
    In app terms that is the top-right cell, and whatever sits there loses its
    routing - so assertions about cabinets have to step around it."""
    return col == section['cols'] - 1 and row == 0


def _decoded_cell(screen, col, app_row):
    """Decoded records are keyed by BINARY row; the app row is the encoder's
    own (binary_row + 1) % rows, the same rotation the round trip reads back."""
    rows = screen['rows']
    for panel in screen['panels']:
        if panel['col'] == col and (panel['row'] + 1) % rows == app_row:
            return panel
    raise AssertionError('no decoded cell (%d,%d)' % (col, app_row))


# ── one canvas, one section, one sending card ────────────────────────────

def test_each_canvas_becomes_one_section_on_its_own_sending_card():
    project = _project(
        [_canvas('c1', 'One'), _canvas('c2', 'Two')],
        [_layer('l1', 'c1', 4, 3), _layer('l2', 'c2', 2, 2)])

    sections = _sections(project)

    assert len(sections) == 2
    # The sending card index is the canvas's position in project['canvases'].
    assert [s['sc_idx'] for s in sections] == [0, 1]
    assert (sections[0]['cols'], sections[0]['rows']) == (4, 3)
    assert (sections[1]['cols'], sections[1]['rows']) == (2, 2)


def test_a_canvas_with_two_layers_is_one_section_holding_both():
    """The regression the old model could not express. Two layers on one canvas
    are cabinets INSIDE one section, not two sections."""
    project = _project(
        [_canvas('c1', 'Shared')],
        [_layer('l1', 'c1', 3, 2, name='left'),
         _layer('l2', 'c1', 2, 2, ox=300, name='right')])

    sections = _sections(project)

    assert len(sections) == 1
    section = sections[0]
    # 3 columns of one layer + 2 of the other, sharing the same two rows.
    assert (section['cols'], section['rows']) == (5, 2)
    live = [p for p in section['panels']
            if not p['hidden'] and not _is_terminator_cell(section, p['col'], p['row'])]
    assert len(live) == 3 * 2 + 2 * 2 - 1  # less the cell the terminator takes


def test_both_layers_ports_survive_on_one_sending_card():
    """A canvas is one sending card, so the second layer's ports cannot also
    start at 1 - they are shifted up instead of colliding."""
    project = _project(
        [_canvas('c1', 'Shared')],
        [_layer('l1', 'c1', 3, 2, name='left'),
         _layer('l2', 'c1', 2, 2, ox=300, name='right')])

    section = _sections(project)[0]
    ports = sorted({p['port_num'] for p in section['panels'] if not p['hidden']})

    assert len(ports) > 1, 'the two layers ended up sharing one port number'
    assert ports == list(range(1, len(ports) + 1))


def test_canvases_without_screen_layers_are_skipped():
    """An empty section is a screen NovaLCT has to draw with nothing in it. The
    skipped canvas still costs its sending card index, so the canvases that do
    export keep the card they would have had."""
    project = _project(
        [_canvas('c1', 'One'), _canvas('c2', 'Empty'), _canvas('c3', 'Three')],
        [_layer('l1', 'c1', 2, 2), _layer('l3', 'c3', 2, 2)])

    sections = _sections(project)

    assert len(sections) == 2
    assert [s['sc_idx'] for s in sections] == [0, 2]


def test_an_image_layer_is_not_a_screen():
    project = _project(
        [_canvas('c1', 'One')],
        [_layer('l1', 'c1', 2, 2),
         {'id': 'i1', 'canvas_id': 'c1', 'type': 'image', 'panels': []}])

    assert len(_sections(project)) == 1


def test_a_project_with_no_screen_layers_at_all_refuses():
    project = _project([_canvas('c1', 'One')], [])
    with pytest.raises(ValueError):
        _sections(project)


# ── placeholders ─────────────────────────────────────────────────────────

def test_hidden_and_blank_cabinets_become_placeholders():
    """A hidden or blank cabinet is a gap in the wall. It reaches the file as
    NovaStar's placeholder - sender 0xFF - rather than a port routed to
    nothing."""
    project = _project(
        [_canvas('c1', 'One')],
        [_layer('l1', 'c1', 3, 3, hidden=[(0, 2)], blank=[(1, 2)])])

    section = _sections(project)[0]

    assert _cell(section, 0, 2)['hidden'] is True
    assert _cell(section, 1, 2)['hidden'] is True
    assert _cell(section, 2, 2)['hidden'] is False

    screen = decode_scr(build_multi_screen_scr(_sections(project)))['screens'][0]
    assert _decoded_cell(screen, 0, 2)['sender'] == 255
    assert _decoded_cell(screen, 1, 2)['sender'] == 255
    assert _decoded_cell(screen, 2, 2)['sender'] != 255


def test_grid_cells_no_cabinet_sits_in_are_placeholders():
    """Two layers on one canvas do not have to tile a rectangle. The encoder
    writes every cell of the bounding grid, and a cell it finds nothing for
    would go out as a REAL cabinet on port 1 - so the holes are filled."""
    project = _project(
        [_canvas('c1', 'One')],
        [_layer('l1', 'c1', 2, 1, name='top'),
         _layer('l2', 'c1', 2, 1, oy=100, ox=200, name='lower right')])

    section = _sections(project)[0]

    assert (section['cols'], section['rows']) == (4, 2)
    # The top layer occupies columns 0-1 of row 0 only, so (2,0) and (3,0)
    # belong to no cabinet at all.
    assert _cell(section, 0, 1)['hidden'] is True
    assert _cell(section, 1, 1)['hidden'] is True


# ── geometry ─────────────────────────────────────────────────────────────

def test_layers_keep_their_own_cabinet_sizes():
    """Real walls mix cabinet sizes, so per-cabinet geometry is passed through
    rather than flattened onto one pitch."""
    project = _project(
        [_canvas('c1', 'Mixed')],
        [_layer('l1', 'c1', 2, 2, cw=100, ch=100, name='big'),
         _layer('l2', 'c1', 2, 2, cw=50, ch=50, ox=200, name='small')])

    section = _sections(project)[0]
    widths = {p['w'] for p in section['panels'] if not p['hidden']}

    assert widths == {100, 50}


def test_panel_coordinates_without_the_layer_offset_are_still_placed():
    """The server writes panel x/y with the layer offset already in them. A
    project that does not is told apart by its leftmost cabinet sitting at 0
    instead of at the offset, and lifted rather than piled on the origin."""
    absolute = _project([_canvas('c1', 'One')],
                        [_layer('l1', 'c1', 2, 2, ox=400, oy=200)])
    relative = _project([_canvas('c1', 'One')],
                        [_layer('l1', 'c1', 2, 2, ox=400, oy=200, relative=True)])

    a = _sections(absolute)[0]
    r = _sections(relative)[0]

    assert (a['screen_x'], a['screen_y']) == (400, 200)
    assert (r['screen_x'], r['screen_y']) == (400, 200)
    assert (a['cols'], a['rows']) == (r['cols'], r['rows'])


def test_the_section_origin_is_where_the_cabinets_start():
    project = _project([_canvas('c1', 'One')],
                       [_layer('l1', 'c1', 2, 2, ox=300, oy=150)])

    section = _sections(project)[0]

    assert (section['screen_x'], section['screen_y']) == (300, 150)


# ── cabling ──────────────────────────────────────────────────────────────

def test_drawn_cables_set_the_chain_order():
    """flowPattern 'custom' means the user drew the runs. The order the cable
    was drawn IS the chain order, so it is walked, not recomputed."""
    paths = {'1': [{'col': 0, 'row': 1}, {'col': 1, 'row': 1}, {'col': 2, 'row': 1}]}
    project = _project(
        [_canvas('c1', 'One')],
        [_layer('l1', 'c1', 3, 2, flowPattern='custom', customPortPaths=paths)])

    section = _sections(project)[0]

    assert [_cell(section, c, 1)['chain_order'] for c in (0, 1, 2)] == [0, 1, 2]
    assert {_cell(section, c, 1)['port_num'] for c in (0, 1, 2)} == {1}


def test_drawn_cables_are_walked_in_numeric_port_order():
    """Port 10 comes after port 9, not after port 1 - which is what sorting the
    string keys would do."""
    paths = {str(n): [{'col': 0, 'row': n - 1}] for n in range(1, 11)}
    project = _project(
        [_canvas('c1', 'One')],
        [_layer('l1', 'c1', 2, 10, flowPattern='custom', customPortPaths=paths)])

    section = _sections(project)[0]

    assert [_cell(section, 0, r)['port_num'] for r in range(10)] == list(range(1, 11))


def test_ports_are_one_based_into_the_encoder():
    """The file stores ports 0-based and the encoder subtracts one, so nothing
    here may hand it a 0-based port. Established by measurement; see
    test_scr_roundtrip.py."""
    project = _project([_canvas('c1', 'One')], [_layer('l1', 'c1', 3, 3)])

    section = _sections(project)[0]
    ports = {p['port_num'] for p in section['panels'] if not p['hidden']}

    assert ports and min(ports) >= 1


# ── the file itself ──────────────────────────────────────────────────────

def test_the_output_survives_its_own_decode():
    """A file that does not decode back to what was written is wrong, whatever
    else it does."""
    project = _project(
        [_canvas('c1', 'One'), _canvas('c2', 'Two')],
        [_layer('l1', 'c1', 5, 4, hidden=[(0, 0), (1, 0)]),
         _layer('l2', 'c2', 3, 3),
         _layer('l3', 'c2', 2, 3, ox=300)])

    sections = _sections(project)
    data = build_multi_screen_scr(sections)

    assert verify(data, sections) == []


def test_the_decoded_file_has_one_screen_per_exporting_canvas():
    project = _project(
        [_canvas('c1', 'One'), _canvas('c2', 'Two'), _canvas('c3', 'Three')],
        [_layer('l1', 'c1', 3, 3), _layer('l2', 'c2', 3, 3), _layer('l3', 'c3', 3, 3)])

    decoded = decode_scr(build_multi_screen_scr(_sections(project)))

    assert len(decoded['screens']) == 3


def test_each_section_is_written_on_its_own_sending_card():
    project = _project(
        [_canvas('c1', 'One'), _canvas('c2', 'Two')],
        [_layer('l1', 'c1', 3, 3), _layer('l2', 'c2', 3, 3)])

    decoded = decode_scr(build_multi_screen_scr(_sections(project)))

    for expected, screen in enumerate(decoded['screens']):
        senders = {p['sender'] for p in screen['panels']
                   if p['sender'] != 255 and p['chain_order'] != 0}
        assert senders <= {expected}, (
            'section %d carries sending cards %s' % (expected, senders))


# ── the origin row ───────────────────────────────────────────────────────
#
# The format reserves the last cell of the top row for the section terminator.
# NovaStar frees it by sliding that whole row one cell LEFT and keeping the
# routing of the cabinet that falls off the left end in the section marker.
# These pin the rule in both directions, because the visible symptom flips
# sign with the direction of the row's run and a blanket offset fixes one wall
# while breaking the next.

def _flow(pattern, cols, rows):
    return _sections(_project(
        [_canvas('c1', 'One')],
        [_layer('l1', 'c1', cols, rows, flowPattern=pattern)]))[0]


def _routing(section, col, row):
    cell = _cell(section, col, row)
    return (cell['port_num'], cell['chain_order'])


def test_a_left_to_right_top_row_slides_one_cell_left():
    """tl-h walks the top row 0,1,2,3. The slide drops link 0 off the left end,
    so the row is written 1,2,3 and the last cell is left for the terminator."""
    section = _flow('tl-h', 4, 3)

    assert [_routing(section, col, 0) for col in range(3)] == [(1, 1), (1, 2), (1, 3)]
    assert _cell(section, 3, 0)['hidden']
    # No other row moves.
    assert [_routing(section, col, 1) for col in range(4)] == [
        (1, 7), (1, 6), (1, 5), (1, 4)]


def test_a_right_to_left_top_row_slides_the_same_way():
    """tr-h walks the same row 3,2,1,0. The slide is still one cell left, so it
    is the run's TAIL that falls off and the row is written 2,1,0 - the same
    correction going the other way round."""
    section = _flow('tr-h', 4, 3)

    assert [_routing(section, col, 0) for col in range(3)] == [(1, 2), (1, 1), (1, 0)]
    assert _cell(section, 3, 0)['hidden']
    assert [_routing(section, col, 1) for col in range(4)] == [
        (1, 4), (1, 5), (1, 6), (1, 7)]


def test_the_marker_carries_the_routing_of_the_cabinet_pushed_off():
    """Section bytes 10-13 are Sender(1) Port(1) ConnectIndex(2 LE) - the tail
    of the 17-byte record the displaced cabinet no longer has a cell for. It is
    the only record of it left in the file."""
    assert _flow('tl-h', 4, 3)['marker'] == (0, 0, 0, 0)     # port 1, link 0
    assert _flow('tr-h', 4, 3)['marker'] == (0, 0, 3, 0)     # port 1, link 3
    assert _flow('tr-h', 5, 2)['marker'] == (0, 0, 4, 0)     # port 1, link 4


def test_a_second_canvas_marks_its_own_sending_card():
    sections = _sections(_project(
        [_canvas('c1', 'One'), _canvas('c2', 'Two')],
        [_layer('l1', 'c1', 4, 3), _layer('l2', 'c2', 4, 3)]))

    assert [s['marker'][0] for s in sections] == [0, 1]


def test_an_empty_top_left_cell_marks_the_placeholder_routing():
    """Nothing to displace, so the marker carries NovaStar's placeholder
    routing - sender 255, port 1, link 1 - the same ff 01 01 00 two of the
    reference sections carry."""
    section = _sections(_project(
        [_canvas('c1', 'One')],
        [_layer('l1', 'c1', 4, 3, hidden={(0, 0)})]))[0]

    assert section['marker'] == (0xFF, 0x01, 0x01, 0x00)


def _chains_by_port(screen):
    """Every non-placeholder record, terminator included - NovaLCT reads that
    one as a cabinet like any other."""
    by_port = collections.defaultdict(list)
    for panel in screen['panels']:
        if panel['sender'] == 255:
            continue
        by_port[panel['port']].append(panel['chain_order'])
    return by_port


def test_a_run_starting_at_link_zero_leaves_every_chain_whole():
    """The terminator is written as sender 0, port 0, link 0. When the top row
    starts its run at link 0 the slide displaces exactly that cabinet, so the
    terminator lands in the hole it left: no port has a gap and nothing is
    doubled."""
    screen = decode_scr(build_multi_screen_scr([_flow('tl-h', 4, 3)]))['screens'][0]

    for port, links in _chains_by_port(screen).items():
        assert sorted(links) == list(range(len(links))), 'port %d: %s' % (port, links)


def test_any_other_run_leaves_one_gap_and_doubles_link_zero():
    """The other direction displaces something that is not link 0, so link 0 is
    still occupied when the terminator claims it and the displaced link is left
    as a hole. Both marks are NovaStar's own - every section in the reference
    corpus is short exactly the link its marker names."""
    section = _flow('tr-h', 4, 3)
    screen = decode_scr(build_multi_screen_scr([section]))['screens'][0]
    displaced_port, displaced_link = section['marker'][1], section['marker'][2]

    by_port = _chains_by_port(screen)
    assert list(by_port) == [displaced_port]
    links = sorted(by_port[displaced_port])
    assert links == [0] + [n for n in range(4 * 3) if n != displaced_link]


# ── warnings ─────────────────────────────────────────────────────────────

def test_an_unpublished_frame_rate_warns_instead_of_inventing_a_map():
    """novastar-armor publishes nothing past 120 Hz. The app draws ERROR rather
    than a plausible port count, and this says so rather than writing a map
    nobody can stand behind."""
    warnings = Warnings()
    project = _project([_canvas('c1', 'One')],
                       [_layer('l1', 'c1', 3, 3, frameRate=240)])

    sections = build_sections(project, warnings)

    assert any('no port capacity' in w for w in warnings.items)
    assert all(p['hidden'] for p in sections[0]['panels'])
