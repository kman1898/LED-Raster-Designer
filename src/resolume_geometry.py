"""
Resolume Advanced Output geometry: what an export unit is, the outline
trace (contours, islands, ring simplification), the Slice/Polygon shape
decision and the XML emitters, ending in generate_resolume_xml.

Pure functions: nothing here reads request state or the live project. The
export unit model (_export_units, _export_unit_bounds) lives at the top
because every exporter - the PSD, the layer ZIP and the Resolume XML -
groups layers the same way, and the shape code below is built on it.

The three names taken from app are plain functions, never reassigned, so a
`from app import` binding is safe here (see routes_preferences.py for why
that is NOT true of the project state). app imports this module at its
bottom, after those helpers exist, and re-exports the names tests import.
"""
from app import _build_panels, _is_hashable, _layer_bounds


def _export_units(project, layers):
    """Split ``layers`` into the units an export draws and names as ONE screen.

    v0.11.0: the whole point of a group is that an outside viewer - Resolume,
    Photoshop, the person holding the print - sees one screen, so a group's
    members must produce a single shape carrying the GROUP's name, not one per
    member.

    Returns ``[(name, [layer, ...]), ...]``. A group takes the slot of its
    FIRST member so the drawing order does not shuffle, and only the members
    present in ``layers`` join it - a member scoped to another canvas exports
    with that canvas, which is the same rule the Resolume screen loop already
    applies. A project with no groups yields one unit per layer in the order
    given, which is exactly the pre-group list and is what keeps every
    existing export byte-identical.

    ``name`` is None when nothing named the unit, so each caller keeps its own
    fallback (Resolume says "Layer", the PSD says "Screen <id>").
    """
    # FIRST duplicate wins, which is the group _find_group resolves and the one
    # _enforce_group_integrity leaves holding the id. This used to be a dict
    # comprehension, so the LAST group with a given id won instead: two groups
    # called 'g1' meant one wall disappeared from the export and its screens
    # were drawn inside the other wall's unit, under the other wall's name.
    # Rule 5 of the integrity pass now prevents the collision upstream; this is
    # the export refusing to differ from _find_group even if one slips through.
    groups = {}
    for g in (project or {}).get('groups') or []:
        if not isinstance(g, dict) or not g.get('id') or not _is_hashable(g.get('id')):
            continue
        groups.setdefault(g['id'], g)
    units = []
    emitted = set()
    for layer in layers or []:
        group_id = layer.get('group_id')
        if not _is_hashable(group_id):
            group_id = None
        group = groups.get(group_id) if group_id else None
        if group is None:
            units.append((layer.get('name'), [layer]))
            continue
        if group_id in emitted:
            continue  # already emitted with its first member
        emitted.add(group_id)
        members = [l for l in layers if l.get('group_id') == group_id]
        units.append((group.get('name') or layer.get('name'), members))
    return units


def _export_unit_bounds(layers):
    """Bounding box of one export unit - a lone layer, or a whole group.

    One layer in, and this is _layer_bounds verbatim, including its
    no-panels fallback to rows/columns * cabinet size.
    """
    members = [l for l in (layers or []) if isinstance(l, dict)]
    if not members:
        return {'x': 0, 'y': 0, 'width': 0, 'height': 0}
    if len(members) == 1:
        return _layer_bounds(members[0])
    boxes = [_layer_bounds(l) for l in members]
    min_x = min(b['x'] for b in boxes)
    min_y = min(b['y'] for b in boxes)
    max_x = max(b['x'] + b['width'] for b in boxes)
    max_y = max(b['y'] + b['height'] for b in boxes)
    return {
        'x': min_x,
        'y': min_y,
        'width': max(0, max_x - min_x),
        'height': max(0, max_y - min_y),
    }


# ── Resolume Advanced Output XML Export ─────────────────────────────

def _resolume_param_range(name, default="0", value="0", min_val="-1", max_val="1", alt_name=None):
    """Generate a Resolume ParamRange XML block."""
    alt = f' altName="{alt_name}"' if alt_name else ''
    return (
        f'\t\t\t\t\t\t\t<ParamRange name="{name}"{alt} T="DOUBLE" default="{default}" value="{value}">\n'
        f'\t\t\t\t\t\t\t\t<PhaseSourceStatic name="PhaseSourceStatic"/>\n'
        f'\t\t\t\t\t\t\t\t<BehaviourDouble name="BehaviourDouble"/>\n'
        f'\t\t\t\t\t\t\t\t<ValueRange name="defaultRange" min="{min_val}" max="{max_val}"/>\n'
        f'\t\t\t\t\t\t\t\t<ValueRange name="minMax" min="{min_val}" max="{max_val}"/>\n'
        f'\t\t\t\t\t\t\t\t<ValueRange name="startStop" min="{min_val}" max="{max_val}"/>\n'
        f'\t\t\t\t\t\t\t</ParamRange>\n'
    )

def _layer_has_hidden_panels(layer):
    """Check if a layer has any hidden (deleted) panels."""
    panels = layer.get('panels', [])
    return any(p.get('hidden', False) for p in panels)


def _compute_panel_contour(layer):
    """Compute the outer boundary contour of visible panels as pixel coordinates.

    Returns a list of (x, y) vertices tracing the boundary clockwise.
    The contour follows the outer edges of the visible panel grid,
    stepping at panel boundaries where the shape changes.
    """
    return _compute_layers_contour([layer])


def _compute_layers_contour(layers):
    """The outline of ONE connected region of these layers' visible panels.

    v0.11.0: a screen group is one screen, so its members trace a SINGLE
    outline rather than one per member. Nothing else changes - the lattice
    below was already built from each panel's own rectangle, so panels of
    different cabinet sizes coming from different layers union exactly the
    way half tiles inside one layer already did. One layer in, and this is
    _compute_panel_contour as it stood before groups existed, point for point.

    A union that is NOT connected - two walls with air between them, or a
    screen cut in half by a column of deleted cabinets - has no single outline,
    and this returns the first island's only. Anything that has to be RIGHT
    about such a unit must call _compute_layers_islands, which returns every
    island; this stays for the connected case and for the callers (and pinned
    tests) that predate islands.
    """
    islands = _compute_layers_islands(layers)
    return islands[0] if islands else []


def _compute_layers_islands(layers):
    """Every connected region of these layers' visible panels, outline traced.

    Returns ``[[(x, y), ...], ...]`` - one closed, axis-aligned, counter-
    clockwise ring per island, in reading order (top to bottom, then left to
    right). A connected union gives exactly one ring and that ring is what
    _compute_layers_contour has always returned.

    Why islands at all: the trace below walks the boundary from one starting
    vertex and stops the moment it closes that ring. On a disconnected union it
    therefore returned ONE island and silently dropped the rest - two walls
    with a gap traced as the right-hand wall alone, which then read as "this is
    a rectangle" and shipped as a plain Slice spanning the gap, and a screen
    split by a hidden column shipped a polygon that masked its left-hand
    cabinets to black. Corner-touching members were worse: the shared vertex
    was reachable from both, so one ring passed through it twice and the result
    was a figure-of-eight, which no warper defines a fill for.

    Cells are grouped 4-connected, so members meeting only at a corner are two
    islands - which is exactly what they physically are.

    Holes are not islands and are not returned: a ring is the OUTER boundary of
    its island. A Resolume contour is a single closed loop and cannot express a
    hole, and it does not need to - the cabinets around a hole still map to
    their own coordinates. Only DISCONNECTED surface needs its own shape.

    Known limit: one CONNECTED island can still pinch shut to a point (a wall
    with knockouts arranged so a notch narrows to nothing, e.g. a bay closed
    off by a single diagonal pair). Its boundary genuinely visits that vertex
    twice and the ring says so, because splitting it there would hand the
    notch back to whichever half kept it. That is one piece of LED with one
    honest outline; it is not the two-separate-walls case above.
    """
    panels = []
    for layer in layers or []:
        panels.extend((layer or {}).get('panels') or [])
    if not panels:
        return []

    # v0.11.0: trace the union of the visible panels' REAL rectangles. The old
    # code walked a uniform row/col * cabinet-size grid, which is a whole
    # cabinet too tall/wide whenever a half tile shrinks a row or column.
    # Every rect comes from the panel's own x/y/width/height, which is where
    # the geometry actually lives (_build_panels collapses a wholly-half row or
    # column and anchors a half tile inside its full-size slot otherwise).
    rects = []
    for p in panels:
        # v0.11.0: exclude blank as well as hidden. The contour is "where the
        # LED surface actually is", and every count that answers that question
        # - cabinet totals, weight, power - filters on `not blank and not
        # hidden` (canvas.js:4640, app-presets.js:1329, app-power.js:1517).
        # The contour used to consider only `hidden`, so a blank cabinet was
        # traced as if it were lit.
        if p.get('hidden', False) or p.get('blank', False):
            continue
        # Contour points ship as integer pixel coordinates in the Resolume XML.
        x1 = int(round(p.get('x', 0)))
        y1 = int(round(p.get('y', 0)))
        x2 = int(round(p.get('x', 0) + p.get('width', 0)))
        y2 = int(round(p.get('y', 0) + p.get('height', 0)))
        if x2 <= x1 or y2 <= y1:
            continue  # zero/negative-size panel covers no area
        rects.append((x1, y1, x2, y2))

    if not rects:
        return []

    # Non-uniform coordinate lattice: every rect edge becomes a grid line, so
    # each band [xs[i], xs[i+1]] x [ys[j], ys[j+1]] is either wholly inside a
    # panel or wholly outside every panel. This degenerates to the plain
    # cabinet grid on a uniform wall and generalises to mixed panel sizes.
    xs = sorted({v for (x1, _y1, x2, _y2) in rects for v in (x1, x2)})
    ys = sorted({v for (_x1, y1, _x2, y2) in rects for v in (y1, y2)})
    x_index = {v: i for i, v in enumerate(xs)}
    y_index = {v: i for i, v in enumerate(ys)}

    # Mark every band cell covered by at least one visible panel.
    visible = set()
    for (x1, y1, x2, y2) in rects:
        for c in range(x_index[x1], x_index[x2]):
            for r in range(y_index[y1], y_index[y2]):
                visible.add((r, c))

    if not visible:
        return []

    # Band index -> real pixel coordinate (was col * cab_w / row * cab_h)
    def panel_x(col):
        """Get pixel X position for band column index."""
        return xs[col]

    def panel_y(row):
        """Get pixel Y position for band row index."""
        return ys[row]

    # Trace the boundary of the visible bands using grid edge walking.
    # This handles concavities and arbitrary shapes correctly.
    # Each ring walks counter-clockwise (matching Resolume convention):
    #   top-right → across top going left → down left side → across bottom → up right side

    # Collect all boundary edges between visible and non-visible cells.
    # An edge is on the boundary if one side is visible and the other is not.
    # Edges are stored as ((x1,y1),(x2,y2)) oriented so the visible cell
    # is on the right side (counter-clockwise winding).

    edges = []
    for (r, c) in visible:
        px = panel_x(c)
        py = panel_y(r)
        px2 = panel_x(c + 1)
        py2 = panel_y(r + 1)

        # Top edge: if cell above (r-1, c) is not visible
        if (r - 1, c) not in visible:
            edges.append(((px2, py), (px, py)))  # right to left (CCW)
        # Bottom edge: if cell below (r+1, c) is not visible
        if (r + 1, c) not in visible:
            edges.append(((px, py2), (px2, py2)))  # left to right (CCW)
        # Left edge: if cell left (r, c-1) is not visible
        if (r, c - 1) not in visible:
            edges.append(((px, py), (px, py2)))  # top to bottom (CCW)
        # Right edge: if cell right (r, c+1) is not visible
        if (r, c + 1) not in visible:
            edges.append(((px2, py2), (px2, py)))  # bottom to top (CCW)

    if not edges:
        return []

    # Build adjacency: for each vertex, map start_point -> [(end_point, edge_idx)]
    from collections import defaultdict
    adj = defaultdict(list)
    for i, (start, end) in enumerate(edges):
        adj[start].append((end, i))

    # Walk every ring, not just the first. The old code took ONE starting
    # vertex, walked until it closed that ring and returned - so a second
    # island was never visited at all. Each pass below starts from the
    # top-right-most vertex among the edges nobody has walked yet, so a
    # disconnected union yields one ring per piece.
    used = set()
    remaining = set(range(len(edges)))
    rings = []
    while remaining:
        start_pt = max((edges[i][0] for i in remaining),
                       key=lambda p: (p[0], -p[1]))
        ring = [start_pt]
        current = start_pt
        # Implied arrival direction at a top-right corner: up the right-hand
        # side, which is how a closed ring really does arrive back there.
        in_dir = (0, -1)
        for _ in range(len(edges) + 1):
            candidates = [(end, idx) for end, idx in adj[current] if idx not in used]
            if not candidates:
                break
            # A simple ring offers exactly one unused edge here and the sort is
            # a no-op. More than one means a PINCH: two parts of the shape meet
            # at a single vertex (two cabinets touching corner to corner is the
            # everyday case). Taking either one at random is how the old walk
            # produced a figure-of-eight that passed through the shared vertex
            # twice - undefined for a warper. Turning towards the surface we are
            # already tracing keeps each lobe a separate, simple ring.
            def turn(candidate, _in_dir=in_dir, _cur=current):
                end = candidate[0]
                out_dir = (_sign(end[0] - _cur[0]), _sign(end[1] - _cur[1]))
                return (_in_dir[0] * out_dir[1] - _in_dir[1] * out_dir[0],
                        out_dir)
            next_pt, edge_idx = min(candidates, key=turn)
            used.add(edge_idx)
            remaining.discard(edge_idx)
            in_dir = (_sign(next_pt[0] - current[0]), _sign(next_pt[1] - current[1]))
            ring.append(next_pt)
            current = next_pt
            if current == start_pt:
                break
        # Remove the closing duplicate
        if len(ring) > 1 and ring[-1] == ring[0]:
            ring.pop()
        # A ring wound the other way is a HOLE, not an island: the surface
        # around a missing cabinet in the middle of a wall still maps to its own
        # coordinates, and a Resolume contour is one closed loop with no way to
        # say "except here". Outer rings come back negative under this edge
        # orientation (see the shoelace sign below).
        if len(ring) >= 4 and _ring_signed_area(ring) < 0:
            rings.append(_simplify_ring(ring))

    # Reading order: top to bottom, then left to right. Deterministic, and it
    # puts the shapes in the Resolume layer list the way the operator reads the
    # wall. A single-island unit is unaffected - there is only one ring.
    rings.sort(key=lambda ring: (min(y for _x, y in ring),
                                 min(x for x, _y in ring)))
    return rings


def _sign(value):
    return 1 if value > 0 else (-1 if value < 0 else 0)


def _ring_signed_area(ring):
    """Twice the shoelace area of a closed ring; negative for an outer ring."""
    total = 0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total


def _simplify_ring(ring):
    """Drop the intermediate points of every straight run."""
    if len(ring) < 3:
        return ring
    simplified = []
    n = len(ring)
    for i in range(n):
        prev = ring[(i - 1) % n]
        curr = ring[i]
        nxt = ring[(i + 1) % n]
        # Keep point if direction changes
        d1 = (_sign(curr[0] - prev[0]), _sign(curr[1] - prev[1]))
        d2 = (_sign(nxt[0] - curr[0]), _sign(nxt[1] - curr[1]))
        if d1 != d2:
            simplified.append(curr)
    return simplified


def _ring_bounds(ring):
    """The bounding box of one traced ring, in the export's bounds shape."""
    if not ring:
        return {'x': 0, 'y': 0, 'width': 0, 'height': 0}
    xs = [x for x, _y in ring]
    ys = [y for _x, y in ring]
    return {
        'x': float(min(xs)), 'y': float(min(ys)),
        'width': float(max(xs) - min(xs)), 'height': float(max(ys) - min(ys)),
    }


def _layer_has_knockouts(layer):
    """Does this layer have any cabinet missing from its grid?

    Hidden (deleted) OR blank. v0.11.0 taught the CONTOUR that a blank cabinet
    is not LED surface but left the SHAPE DECISION on the old hidden-only test,
    so a lone screen with a blanked corner traced a correct six-vertex outline
    and then threw it away and shipped a full rectangle - while the same wall
    grouped with a neighbour correctly became a polygon. Two crews with the
    same wall got two different Resolume files depending on whether anyone had
    pressed Group Screens.
    """
    panels = layer.get('panels', []) if isinstance(layer, dict) else []
    return any(p.get('hidden', False) or p.get('blank', False)
               for p in panels if isinstance(p, dict))


def _export_unit_needs_polygon(members):
    """Does this export unit need a Polygon, or is a plain Slice enough?

    A lone layer keeps the pre-v0.11.0 test: a cabinet missing anywhere in the
    grid and it is a Polygon, so every mapping already in the field re-exports
    unchanged. (What CHANGED in v0.11.0: "missing" now means blank as well as
    hidden, matching the contour - see _layer_has_knockouts.)

    v0.11.0: a group is judged on the union it actually traces, because no
    member can answer the question on its own. Two rectangular members that
    tile into a rectangle ARE a rectangle and ship as a Slice; two that tile
    into an L are a polygon even though neither member has a hidden panel.
    A traced contour with four vertices is a rectangle: the trace is
    axis-aligned and collinear points are already simplified away, so a
    concave shape can never come back with fewer than six.

    Disconnected units do not go through here at all - they ship one shape per
    island (see _export_unit_shapes), and each island answers this question for
    itself on its own ring.
    """
    if len(members) == 1 and len(_compute_layers_islands(members)) <= 1:
        return _layer_has_knockouts(members[0])
    return len(_compute_layers_contour(members)) != 4


def _export_unit_shapes(members):
    """The shape(s) one export unit ships as: ``[(needs_polygon, contour, bounds), ...]``.

    Normally one entry - a lone screen, or a group whose members tile into one
    connected wall. That entry carries the unit's own bounds (_export_unit_bounds,
    i.e. _layer_bounds for a lone layer, nominal fallback and all), so every
    export that worked before is byte-for-byte what it was.

    More than one entry when the unit's LED surface is DISCONNECTED: two group
    members with air between them, three members with one parked off to the
    side, or a single screen cut in two by a column of deleted cabinets. One
    shape cannot honestly describe two separate walls:

      * as a Slice it claims the gap, so a third of the picture is mapped onto
        empty air between the walls and neither wall can be positioned on its
        own afterwards;
      * as a Polygon it can only carry ONE closed contour, so whichever island
        is not in it is masked off and those cabinets go black. That is exactly
        what a screen split by a hidden column did.

    So each island gets its own shape, at its own coordinates, all carrying the
    unit's name - which is what two ungrouped walls already produce today and
    what an operator expects to find in the Resolume layer list. Input and
    output rectangles stay equal, so content still lands pixel-for-pixel where
    the pixel map says it does; nothing is shifted and nothing is invented.
    An island that is a plain rectangle is a Slice, one that is not is a
    Polygon, judged per island on its own ring.
    """
    islands = _compute_layers_islands(members)
    if len(islands) <= 1:
        contour = islands[0] if islands else []
        return [(_export_unit_needs_polygon(members), contour,
                 _export_unit_bounds(members))]
    return [(len(ring) != 4, ring, _ring_bounds(ring)) for ring in islands]


def _xml_attr(value):
    """Escape a value for use inside a double-quoted XML attribute.

    "Left & Right" is a completely normal name for a wall, and interpolating it
    raw produced a file Resolume simply cannot open. The canvas name has always
    been escaped here; the shape names were not.
    """
    return (str(value)
            .replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _resolume_polygon(layer, unique_id, members=None, name=None,
                      bounds=None, contour=None):
    """Generate a Resolume Polygon XML block for a non-rectangular layer.

    v0.11.0: ``members`` is the export unit this shape covers - a screen
    group's members, or just ``layer``. ``name`` overrides the shape's name so
    a group is named once, for the group.

    ``bounds``/``contour`` override the geometry, which is how a unit whose
    surface is disconnected ships one shape per island (_export_unit_shapes).
    Omitted, they are computed exactly as before.
    """
    members = members or [layer]
    bounds = _export_unit_bounds(members) if bounds is None else bounds
    x1 = int(bounds['x'])
    y1 = int(bounds['y'])
    x2 = x1 + int(bounds['width'])
    y2 = y1 + int(bounds['height'])
    name = _xml_attr(layer.get('name', 'Layer') if name is None else name)

    # Output params (no BRed/BGreen/BBlue for Polygon)
    output_params = (
        _resolume_param_range("Brightness") +
        _resolume_param_range("Contrast") +
        _resolume_param_range("Red") +
        _resolume_param_range("Green") +
        _resolume_param_range("Blue") +
        f'\t\t\t\t\t\t\t<Param name="Is Key" T="BOOL" default="0" value="0"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Black BG" T="BOOL" default="0" value="0"/>\n'
    )

    # Compute contour (over the whole unit - a group traces one outline)
    contour_pts = _compute_layers_contour(members) if contour is None else contour

    def contour_xml(pts, indent):
        lines = f'{indent}<points>\n'
        for x, y in pts:
            lines += f'{indent}\t<v x="{x}" y="{y}"/>\n'
        lines += f'{indent}</points>\n'
        lines += f'{indent}<segments>{"L" * len(pts)}</segments>\n'
        return lines

    input_contour = contour_xml(contour_pts, '\t\t\t\t\t\t\t')
    output_contour = contour_xml(contour_pts, '\t\t\t\t\t\t\t')

    return (
        f'\t\t\t\t\t<Polygon uniqueId="{unique_id}" IsVirgin="0">\n'
        f'\t\t\t\t\t\t<Params name="Common">\n'
        f'\t\t\t\t\t\t\t<Param name="Name" T="STRING" default="Layer" value="{name}"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Enabled" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<Params name="Input">\n'
        f'\t\t\t\t\t\t\t<ParamChoice name="Input Source" default="0:1" value="0:1" storeChoices="0"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Input Opacity" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Input Bypass/Solo" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<Params name="Output">\n'
        f'\t\t\t\t\t\t\t<Param name="Flip" T="UINT8" default="0" value="0"/>\n'
        f'{output_params}'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<InputRect orientation="0">\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t</InputRect>\n'
        f'\t\t\t\t\t\t<OutputRect orientation="0">\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t</OutputRect>\n'
        f'\t\t\t\t\t\t<InputContour closed="1">\n'
        f'{input_contour}'
        f'\t\t\t\t\t\t</InputContour>\n'
        f'\t\t\t\t\t\t<OutputContour closed="1">\n'
        f'{output_contour}'
        f'\t\t\t\t\t\t</OutputContour>\n'
        f'\t\t\t\t\t</Polygon>\n'
    )


def _resolume_slice(layer, unique_id, members=None, name=None, bounds=None,
                    contour=None):
    """Generate a Resolume Slice XML block for a layer.

    v0.11.0: ``members``/``name`` as in _resolume_polygon - a group that tiles
    into a plain rectangle is one Slice over the union, named for the group.
    ``bounds`` overrides the rectangle (one island of a disconnected unit);
    ``contour`` is accepted and ignored so both shape builders take the same
    call.
    """
    members = members or [layer]
    bounds = _export_unit_bounds(members) if bounds is None else bounds
    x1 = float(bounds['x'])
    y1 = float(bounds['y'])
    x2 = x1 + float(bounds['width'])
    y2 = y1 + float(bounds['height'])
    name = _xml_attr(layer.get('name', 'Layer') if name is None else name)
    w = x2 - x1
    h = y2 - y1

    # Output params block (Brightness, Contrast, RGB, etc.)
    output_params = (
        _resolume_param_range("Brightness") +
        _resolume_param_range("Contrast") +
        _resolume_param_range("Red") +
        _resolume_param_range("Green") +
        _resolume_param_range("Blue") +
        f'\t\t\t\t\t\t\t<Param name="Is Key" T="BOOL" default="0" value="0"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Black BG" T="BOOL" default="0" value="0"/>\n' +
        _resolume_param_range("BRed", alt_name="Red", min_val="0", max_val="0.4000000000000000222") +
        _resolume_param_range("BGreen", alt_name="Green", min_val="0", max_val="0.4000000000000000222") +
        _resolume_param_range("BBlue", alt_name="Blue", min_val="0", max_val="0.4000000000000000222")
    )

    # 4x4 BezierWarper grid (linear, 3 divisions)
    bezier_verts = ""
    for ry in range(4):
        for rx in range(4):
            bx = x1 + (w * rx / 3.0)
            by = y1 + (h * ry / 3.0)
            bezier_verts += f'\t\t\t\t\t\t\t\t\t<v x="{bx}" y="{by}"/>\n'

    return (
        f'\t\t\t\t\t<Slice uniqueId="{unique_id}">\n'
        f'\t\t\t\t\t\t<Params name="Common">\n'
        f'\t\t\t\t\t\t\t<Param name="Name" T="STRING" default="Layer" value="{name}"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Enabled" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<Params name="Input">\n'
        f'\t\t\t\t\t\t\t<ParamChoice name="Input Source" default="0:1" value="0:1" storeChoices="0"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Input Opacity" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t\t<Param name="Input Bypass/Solo" T="BOOL" default="1" value="1"/>\n'
        f'\t\t\t\t\t\t\t<Param name="SoftEdgeEnable" T="BOOL" default="0" value="0"/>\n'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<Params name="Output">\n'
        f'\t\t\t\t\t\t\t<Param name="Flip" T="UINT8" default="0" value="0"/>\n'
        f'{output_params}'
        f'\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t<InputRect orientation="0">\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t</InputRect>\n'
        f'\t\t\t\t\t\t<OutputRect orientation="0">\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t</OutputRect>\n'
        f'\t\t\t\t\t\t<Warper>\n'
        f'\t\t\t\t\t\t\t<Params name="Warper">\n'
        f'\t\t\t\t\t\t\t\t<ParamChoice name="Point Mode" default="PM_LINEAR" value="PM_LINEAR" storeChoices="0"/>\n'
        f'\t\t\t\t\t\t\t\t<Param name="Flip" T="UINT8" default="0" value="0"/>\n'
        f'\t\t\t\t\t\t\t</Params>\n'
        f'\t\t\t\t\t\t\t<BezierWarper controlWidth="4" controlHeight="4">\n'
        f'\t\t\t\t\t\t\t\t<vertices>\n'
        f'{bezier_verts}'
        f'\t\t\t\t\t\t\t\t</vertices>\n'
        f'\t\t\t\t\t\t\t</BezierWarper>\n'
        f'\t\t\t\t\t\t\t<Homography>\n'
        f'\t\t\t\t\t\t\t\t<src>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t\t</src>\n'
        f'\t\t\t\t\t\t\t\t<dst>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x1}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x2}" y="{y1}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x2}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t\t\t<v x="{x1}" y="{y2}"/>\n'
        f'\t\t\t\t\t\t\t\t</dst>\n'
        f'\t\t\t\t\t\t\t</Homography>\n'
        f'\t\t\t\t\t\t</Warper>\n'
        f'\t\t\t\t\t</Slice>\n'
    )

def generate_resolume_xml(project, project_name, raster_w, raster_h):
    """Generate Resolume Arena Advanced Output XML from project layers.

    v0.8 (Slice 11): one <Screen> per project canvas. Each Screen's layers
    are the screen-type layers belonging to that canvas; coordinates inside
    the Polygon/Slice are CANVAS-LOCAL (panel.x/y are stored that way after
    Slice 6), which matches the per-canvas Resolume composition model. The
    OutputDeviceVirtual for each Screen is sized to that canvas's raster.

    The project-wide CurrentCompositionTextureSize is the workspace bounding
    box of all visible canvases, that's the source-composition size the
    user would feed in Resolume to drive every canvas at once.

    Legacy projects (no canvases array) fall through to a single synthetic
    Screen using the project-root raster dimensions, byte-equivalent to the
    pre-Slice-11 export so v0.7 workflows aren't disrupted.
    """
    import random

    layers = project.get('layers', [])
    # Filter to visible screen layers only
    screen_layers = [l for l in layers if l.get('type') == 'screen' and l.get('visible', True)]

    # Build panels for layers that don't have them
    for layer in screen_layers:
        if not layer.get('panels'):
            layer['panels'] = _build_panels(layer)

    # Resolve canvases. Visible only, hiding a canvas in the sidebar is
    # the user's signal that it shouldn't appear in the export. Legacy:
    # synthetic single canvas at (0, 0) using project-root raster.
    project_canvases = project.get('canvases') or []
    if project_canvases:
        export_canvases = [
            c for c in project_canvases
            if isinstance(c, dict) and c.get('visible', True) is not False
        ]
    else:
        export_canvases = [{
            'id': None,
            'name': 'Screen 1',
            'workspace_x': 0,
            'workspace_y': 0,
            'raster_width': raster_w,
            'raster_height': raster_h,
        }]

    # Workspace bounding box -> CurrentCompositionTextureSize. If no canvases
    # have content yet, fall back to the client-supplied raster_w/h (which
    # comes from the toolbar, i.e. the active canvas).
    if export_canvases:
        min_x = min((c.get('workspace_x') or 0) for c in export_canvases)
        min_y = min((c.get('workspace_y') or 0) for c in export_canvases)
        max_x = max((c.get('workspace_x') or 0) + (c.get('raster_width') or 0)
                    for c in export_canvases)
        max_y = max((c.get('workspace_y') or 0) + (c.get('raster_height') or 0)
                    for c in export_canvases)
        composition_w = max(int(max_x - min_x), int(raster_w))
        composition_h = max(int(max_y - min_y), int(raster_h))
    else:
        composition_w, composition_h = int(raster_w), int(raster_h)

    # Screen-level output params (used for every Screen block)
    def screen_param_range(name, default="0", value="0", min_val="-1", max_val="1"):
        return (
            f'\t\t\t\t\t<ParamRange name="{name}" T="DOUBLE" default="{default}" value="{value}">\n'
            f'\t\t\t\t\t\t<PhaseSourceStatic name="PhaseSourceStatic"/>\n'
            f'\t\t\t\t\t\t<BehaviourDouble name="BehaviourDouble"/>\n'
            f'\t\t\t\t\t\t<ValueRange name="defaultRange" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t\t\t\t<ValueRange name="minMax" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t\t\t\t<ValueRange name="startStop" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t\t\t</ParamRange>\n'
        )

    screen_output = (
        screen_param_range("Opacity", "1", "1", "0", "1") +
        screen_param_range("Brightness") +
        screen_param_range("Contrast") +
        screen_param_range("Red") +
        screen_param_range("Green") +
        screen_param_range("Blue")
    )

    # Virtual output device params
    def device_param_range(name, default, value, max_val="16384"):
        return (
            f'\t\t\t\t\t\t<ParamRange name="{name}" T="DOUBLE" default="{default}" value="{value}">\n'
            f'\t\t\t\t\t\t\t<PhaseSourceStatic name="PhaseSourceStatic"/>\n'
            f'\t\t\t\t\t\t\t<BehaviourDouble name="BehaviourDouble"/>\n'
            f'\t\t\t\t\t\t\t<ValueRange name="defaultRange" min="1" max="{max_val}"/>\n'
            f'\t\t\t\t\t\t\t<ValueRange name="minMax" min="1" max="{max_val}"/>\n'
            f'\t\t\t\t\t\t\t<ValueRange name="startStop" min="1" max="{max_val}"/>\n'
            f'\t\t\t\t\t\t</ParamRange>\n'
        )

    # Build one <Screen> per canvas with its scoped layers.
    screens_xml = ""
    for canvas in export_canvases:
        canvas_id = canvas.get('id')
        canvas_name = canvas.get('name') or 'Screen'
        canvas_w = int(canvas.get('raster_width') or raster_w)
        canvas_h = int(canvas.get('raster_height') or raster_h)
        # Screen-scoped layers: visible screen-type layers in this canvas.
        # Legacy synthetic canvas (id=None) takes every visible layer so
        # pre-multi-canvas projects export identically to v0.7.
        if canvas_id:
            canvas_layers = [l for l in screen_layers if l.get('canvas_id') == canvas_id]
        else:
            canvas_layers = screen_layers

        # v0.11.0: one shape per export unit, not per layer. A screen group's
        # members become a single Slice/Polygon over their union, carrying the
        # group's name; an ungrouped project yields the old per-layer list.
        slices_xml = ""
        for unit_name, members in _export_units(project, canvas_layers):
            # Usually one shape. A unit whose LED surface is in two or more
            # disconnected pieces ships one shape per piece, all named for the
            # unit - see _export_unit_shapes for why one shape cannot do it.
            for needs_polygon, contour, bounds in _export_unit_shapes(members):
                slice_id = random.randint(1000000000000, 9999999999999)
                build = _resolume_polygon if needs_polygon else _resolume_slice
                slices_xml += build(members[0], slice_id, members, unit_name,
                                    bounds=bounds, contour=contour)

        screen_unique_id = random.randint(1000000000000, 9999999999999)
        device_hash = random.randint(1000000000000000000, 9999999999999999999)
        # Escape any "&", quote chars in the canvas name for XML attributes.
        safe_name = _xml_attr(canvas_name)

        screens_xml += (
            f'\t\t\t<Screen name="{safe_name}" uniqueId="{screen_unique_id}">\n'
            f'\t\t\t\t<Params name="Params">\n'
            f'\t\t\t\t\t<Param name="Name" T="STRING" default="" value="{safe_name}"/>\n'
            f'\t\t\t\t\t<Param name="Enabled" T="BOOL" default="1" value="1"/>\n'
            f'\t\t\t\t\t<Param name="Hidden" T="BOOL" default="0" value="0"/>\n'
            f'\t\t\t\t</Params>\n'
            f'\t\t\t\t<Params name="Output">\n'
            f'{screen_output}'
            f'\t\t\t\t</Params>\n'
            f'\t\t\t\t<guides>\n'
            f'\t\t\t\t\t<ScreenGuide name="ScreenGuide" type="0">\n'
            f'\t\t\t\t\t\t<Params name="Params">\n'
            f'\t\t\t\t\t\t\t<ParamPixels name="Image"/>\n'
            f'\t\t\t\t\t\t\t<ParamRange name="Opacity" T="DOUBLE" default="0.25" value="0.25">\n'
            f'\t\t\t\t\t\t\t\t<PhaseSourceStatic name="PhaseSourceStatic"/>\n'
            f'\t\t\t\t\t\t\t\t<BehaviourDouble name="BehaviourDouble"/>\n'
            f'\t\t\t\t\t\t\t\t<ValueRange name="defaultRange" min="0" max="1"/>\n'
            f'\t\t\t\t\t\t\t\t<ValueRange name="minMax" min="0" max="1"/>\n'
            f'\t\t\t\t\t\t\t\t<ValueRange name="startStop" min="0" max="1"/>\n'
            f'\t\t\t\t\t\t\t</ParamRange>\n'
            f'\t\t\t\t\t\t</Params>\n'
            f'\t\t\t\t\t</ScreenGuide>\n'
            f'\t\t\t\t</guides>\n'
            f'\t\t\t\t<layers>\n'
            f'{slices_xml}'
            f'\t\t\t\t</layers>\n'
            f'\t\t\t\t<OutputDevice>\n'
            f'\t\t\t\t\t<OutputDeviceVirtual name="{safe_name}" deviceId="Virtual{safe_name}" idHash="{device_hash}" width="{canvas_w}" height="{canvas_h}">\n'
            f'\t\t\t\t\t\t<Params name="Params">\n'
            f'{device_param_range("Width", "800", str(canvas_w))}'
            f'{device_param_range("Height", "600", str(canvas_h))}'
            f'\t\t\t\t\t\t</Params>\n'
            f'\t\t\t\t\t</OutputDeviceVirtual>\n'
            f'\t\t\t\t</OutputDevice>\n'
            f'\t\t\t</Screen>\n'
        )

    # SoftEdging params
    def soft_edge_param(name, default, value, min_val, max_val):
        return (
            f'\t\t\t<ParamRange name="{name}" T="DOUBLE" default="{default}" value="{value}">\n'
            f'\t\t\t\t<PhaseSourceStatic name="PhaseSourceStatic"/>\n'
            f'\t\t\t\t<BehaviourDouble name="BehaviourDouble"/>\n'
            f'\t\t\t\t<ValueRange name="defaultRange" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t\t<ValueRange name="minMax" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t\t<ValueRange name="startStop" min="{min_val}" max="{max_val}"/>\n'
            f'\t\t\t</ParamRange>\n'
        )

    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<XmlState name="{project_name}">\n'
        f'\t<versionInfo name="Resolume Arena" majorVersion="7" minorVersion="24" microVersion="3" revision="63742"/>\n'
        f'\t<ScreenSetup name="ScreenSetup">\n'
        f'\t\t<Params name="ScreenSetupParams"/>\n'
        f'\t\t<CurrentCompositionTextureSize width="{composition_w}" height="{composition_h}"/>\n'
        f'\t\t<screens>\n'
        f'{screens_xml}'
        f'\t\t</screens>\n'
        f'\t\t<SoftEdging>\n'
        f'\t\t\t<Params name="Soft Edge">\n'
        f'{soft_edge_param("Gamma Red", "2", "2", "1", "3")}'
        f'{soft_edge_param("Gamma Green", "2", "2", "1", "3")}'
        f'{soft_edge_param("Gamma Blue", "2", "2", "1", "3")}'
        f'{soft_edge_param("Gamma", "1", "1", "0", "1")}'
        f'{soft_edge_param("Luminance", "0.5", "0.5", "0", "1")}'
        f'{soft_edge_param("Power", "2", "1.999999999999999778", "0.10000000000000000555", "7")}'
        f'\t\t\t</Params>\n'
        f'\t\t</SoftEdging>\n'
        f'\t</ScreenSetup>\n'
        f'</XmlState>\n'
    )
    return xml
