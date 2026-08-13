"""Adversarial coverage for the v0.10.8.1 server-side geometry rebuild in
``restore_project`` (PUT /api/project).

PUT /api/project is the endpoint behind BOTH undo/redo and file load, and it
now re-derives every screen layer's panel geometry from the per-panel states
the client sent (``app._rebuild_layer_geometry_from_panel_states`` ->
``app._build_panels``). That is a destructive-by-design operation: every panel
field (id, number, row, col, x, y, width, height, blank, hidden, halfTile,
is_color1) is recomputed from (rows, columns, offset_x/y, cabinet size, states).

These tests are written to break that assumption, not to confirm it:

* idempotency - restoring the SAME project two and three times must not drift
* no-op - restoring a project straight out of GET must not touch panels
* self-healing - stale bulk-half-tile geometry must be corrected
* non-screen layers - image/text layers must round-trip untouched
* legacy half flags - the one-way migration must not double-apply on undo
* edge cases - malformed layers must not 500
* cost - the rebuild must not make undo sluggish
"""

import json
import time

import pytest

import app as app_module


# ── helpers ───────────────────────────────────────────────────────────────

def _add_screen(client, name='S1', columns=4, rows=3, cw=128, ch=128, **extra):
    payload = {
        'name': name, 'columns': columns, 'rows': rows,
        'cabinet_width': cw, 'cabinet_height': ch,
    }
    payload.update(extra)
    resp = client.post('/api/layer/add', json=payload)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def _get_project(client):
    resp = client.get('/api/project')
    assert resp.status_code == 200
    return resp.get_json()


def _put(client, project):
    resp = client.put('/api/project', json=project)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def _clean(project):
    """Drop transient/expected-to-change keys so equality means 'same design'."""
    p = json.loads(json.dumps(project))
    p.pop('_migration_notice', None)
    return p


def _panels_of(project, index=0):
    return project['layers'][index].get('panels')


def _panel_map(project):
    """{layer_id: panels} for every layer, for whole-project comparisons."""
    return {l.get('id'): l.get('panels') for l in project.get('layers', [])}


def _set_half_tiles(client, layer_id, targets):
    """targets: {(row, col): 'width'|'height'|'none'} - via the real bulk route,
    which rebuilds geometry server-side, so the result is well-formed."""
    project = _get_project(client)
    layer = next(l for l in project['layers'] if l['id'] == layer_id)
    by_rc = {(p['row'], p['col']): p['id'] for p in layer['panels']}
    body = {'panels': [{'id': by_rc[rc], 'halfTile': v} for rc, v in targets.items()]}
    resp = client.post(f'/api/layer/{layer_id}/panels/set_half_tile', json=body)
    assert resp.status_code == 200, resp.get_data(as_text=True)


def _hide(client, layer_id, rc_list):
    project = _get_project(client)
    layer = next(l for l in project['layers'] if l['id'] == layer_id)
    by_rc = {(p['row'], p['col']): p['id'] for p in layer['panels']}
    for rc in rc_list:
        resp = client.post(
            f'/api/layer/{layer_id}/panel/{by_rc[rc]}/toggle_hidden')
        assert resp.status_code == 200


def _blank(client, layer_id, rc_list):
    project = _get_project(client)
    layer = next(l for l in project['layers'] if l['id'] == layer_id)
    by_rc = {(p['row'], p['col']): p['id'] for p in layer['panels']}
    for rc in rc_list:
        resp = client.post(f'/api/layer/{layer_id}/panel/{by_rc[rc]}/toggle')
        assert resp.status_code == 200


def _assert_idempotent(client, project, label):
    """PUT three times; runs 2 and 3 must be byte-identical to run 1's panels
    AND to run 1's whole project (so flag drift is caught too)."""
    r1 = _clean(_put(client, project))
    r2 = _clean(_put(client, r1))
    r3 = _clean(_put(client, r2))
    assert _panel_map(r2) == _panel_map(r1), (
        f'{label}: second restore CHANGED panel geometry\n'
        f'  1st: {json.dumps(_panel_map(r1), sort_keys=True)}\n'
        f'  2nd: {json.dumps(_panel_map(r2), sort_keys=True)}'
    )
    assert _panel_map(r3) == _panel_map(r1), f'{label}: third restore drifted'
    assert r2 == r1, f'{label}: second restore changed non-panel project data'
    assert r3 == r2, f'{label}: third restore changed non-panel project data'
    return r1


# ── scenario builders (each returns a well-formed project from the server) ──

def _scenario_plain(client):
    _add_screen(client, 'Plain', columns=4, rows=3)
    return _get_project(client)


def _scenario_full_half_row(client):
    layer = _add_screen(client, 'FullHalfRow', columns=4, rows=3)
    _set_half_tiles(client, layer['id'], {(1, c): 'height' for c in range(4)})
    return _get_project(client)


def _scenario_mixed_row(client):
    layer = _add_screen(client, 'MixedRow', columns=4, rows=3)
    _set_half_tiles(client, layer['id'], {(1, 0): 'height', (1, 2): 'height'})
    return _get_project(client)


def _scenario_half_width_column(client):
    layer = _add_screen(client, 'HalfWidthCol', columns=4, rows=3)
    _set_half_tiles(client, layer['id'], {(r, 0): 'width' for r in range(3)})
    return _get_project(client)


def _scenario_hidden_and_blank(client):
    layer = _add_screen(client, 'HiddenBlank', columns=4, rows=3)
    _hide(client, layer['id'], [(0, 0), (2, 3)])
    _blank(client, layer['id'], [(1, 1)])
    return _get_project(client)


def _scenario_half_next_to_hidden(client):
    """Half-tile in a MIXED row whose vertical neighbours are hidden - this is
    the ``_has_visible_neighbor`` anchoring branch in _build_panels."""
    layer = _add_screen(client, 'HalfNextToHidden', columns=3, rows=3)
    _hide(client, layer['id'], [(0, 1)])
    _set_half_tiles(client, layer['id'], {(1, 1): 'height'})
    return _get_project(client)


SCENARIOS = {
    'plain': _scenario_plain,
    'full_half_row': _scenario_full_half_row,
    'mixed_row': _scenario_mixed_row,
    'half_width_column': _scenario_half_width_column,
    'hidden_and_blank': _scenario_hidden_and_blank,
    'half_next_to_hidden': _scenario_half_next_to_hidden,
}


# ── 1. IDEMPOTENCY ────────────────────────────────────────────────────────

@pytest.mark.parametrize('name', sorted(SCENARIOS))
def test_restore_is_idempotent(client, name):
    """Restoring the same project twice (and three times) must not change it.

    If this fails, every undo silently mutates the user's design.
    """
    project = SCENARIOS[name](client)
    _assert_idempotent(client, project, name)


@pytest.mark.parametrize('name', sorted(SCENARIOS))
def test_restore_of_server_state_is_a_no_op(client, name):
    """The stated contract: 'this is a no-op when the incoming geometry
    already agrees'. Take the project straight out of GET (i.e. exactly what
    the server itself built) and restore it - panels must be untouched."""
    project = SCENARIOS[name](client)
    before = _panel_map(project)
    after = _panel_map(_put(client, project))
    assert after == before, (
        f'{name}: restore rewrote geometry the server itself produced\n'
        f'  before: {json.dumps(before, sort_keys=True)}\n'
        f'  after:  {json.dumps(after, sort_keys=True)}'
    )
    # Byte-identical, not merely ==, so an int -> float type flip (which
    # would churn every saved .json file) is caught too.
    assert json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True)


def test_restore_preserves_panel_identity_fields(client):
    """id / number / row / col / is_color1 must survive a restore untouched."""
    _add_screen(client, 'Ident', columns=5, rows=4)
    project = _get_project(client)
    before = [
        {k: p[k] for k in ('id', 'number', 'row', 'col', 'is_color1')}
        for p in _panels_of(project)
    ]
    after = [
        {k: p[k] for k in ('id', 'number', 'row', 'col', 'is_color1')}
        for p in _panels_of(_put(client, project))
    ]
    assert after == before


def test_restore_preserves_layer_offset_and_panel_origin(client):
    """A moved layer must stay moved: panel x/y are anchored to offset_x/y."""
    layer = _add_screen(client, 'Moved', columns=3, rows=2, offset_x=500,
                        offset_y=300)
    project = _get_project(client)
    restored = _put(client, project)
    panels = _panels_of(restored)
    assert min(p['x'] for p in panels) == 500
    assert min(p['y'] for p in panels) == 300
    assert restored['layers'][0]['offset_x'] == 500
    assert layer['id'] == restored['layers'][0]['id']


def test_restore_preserves_hidden_and_blank_state(client):
    project = _scenario_hidden_and_blank(client)
    restored = _put(client, project)
    by_rc = {(p['row'], p['col']): p for p in _panels_of(restored)}
    assert by_rc[(0, 0)]['hidden'] is True
    assert by_rc[(2, 3)]['hidden'] is True
    assert by_rc[(1, 1)]['blank'] is True
    assert by_rc[(0, 1)]['hidden'] is False
    assert by_rc[(0, 1)]['blank'] is False


# ── 1b. DEFECT: hiding a neighbour after a half-tile makes undo move it ────

def _half_then_hide(client, half_kind):
    """Real user ordering: set a half-tile FIRST, then hide the neighbour on
    the side the half-tile is anchored away from.

    ``toggle_panel_hidden`` / ``set_panels_hidden`` rebuild geometry as of
    v0.10.8.1, so the server's own state already carries the new anchoring and
    the restore_project rebuild has nothing left to change. Before that fix the
    routes skipped the rebuild and the panel jumped half a cabinet on the next
    undo/redo or file load, long after the edit that caused it.
    """
    layer = _add_screen(client, 'Anchor', columns=3, rows=3)
    lid = layer['id']
    by_rc = {(p['row'], p['col']): p['id'] for p in layer['panels']}
    client.post(f'/api/layer/{lid}/panels/set_half_tile',
                json={'panels': [{'id': by_rc[(1, 1)], 'halfTile': half_kind}]})
    neighbour = (0, 1) if half_kind == 'height' else (1, 0)
    client.post(f'/api/layer/{lid}/panel/{by_rc[neighbour]}/toggle_hidden')
    return _get_project(client)


@pytest.mark.parametrize('half_kind,axis', [('height', 'y'), ('width', 'x')])
def test_hiding_neighbour_after_half_tile_does_not_move_it_on_undo(
        client, half_kind, axis):
    project = _half_then_hide(client, half_kind)
    before = {(p['row'], p['col']): p[axis] for p in _panels_of(project)}
    # The hidden neighbour removed the anchor on that side, so the half-tile
    # must ALREADY sit against its remaining neighbour in the server's own
    # state - not only after a restore. Pins the fix to the hidden routes;
    # merely dropping the restore_project rebuild would not satisfy this.
    assert before[(1, 1)] == 192, (
        f'half {half_kind} next to a hidden neighbour was not re-anchored by '
        f'the hidden-toggle route: {axis}={before[(1, 1)]}, expected 192')
    after = {(p['row'], p['col']): p[axis]
             for p in _panels_of(_put(client, project))}
    moved = {rc: (before[rc], after[rc]) for rc in before if before[rc] != after[rc]}
    assert not moved, f'restore moved panels {moved} along {axis}'


@pytest.mark.parametrize('half_kind', ['height', 'width'])
def test_hidden_neighbour_anchoring_is_stable_after_the_first_restore(
        client, half_kind):
    """Whatever the re-anchor does, it must converge on the first restore."""
    _assert_idempotent(client, _half_then_hide(client, half_kind),
                       f'half {half_kind} + hidden neighbour')


# ── 1d. the hidden routes' RESPONSE contract (client history depends on it) ─
#
# The client snapshots history right after these calls. If the response does
# not carry the rebuilt layer, the snapshot pairs the new hidden flags with the
# pre-rebuild geometry - exactly the v0.10.8 bulk-half-tile bug - and the next
# undo PUTs that mismatch back. So the routes must RETURN the rebuilt layer,
# not just emit it over the socket.

def _screen_with_half_and_neighbour(client, half_kind='height'):
    """3x3 screen, panel (1,1) half, returns (layer_id, {(row, col): id})."""
    layer = _add_screen(client, 'RespContract', columns=3, rows=3)
    by_rc = {(p['row'], p['col']): p['id'] for p in layer['panels']}
    resp = client.post(
        f'/api/layer/{layer["id"]}/panels/set_half_tile',
        json={'panels': [{'id': by_rc[(1, 1)], 'halfTile': half_kind}]})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return layer['id'], by_rc


def test_set_panels_hidden_returns_rebuilt_layer(client):
    layer_id, by_rc = _screen_with_half_and_neighbour(client)
    resp = client.post(f'/api/layer/{layer_id}/panels/set_hidden',
                       json={'panels': [{'id': by_rc[(0, 1)], 'hidden': True}]})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body['updated'] == 1
    assert 'layer' in body, (
        'set_panels_hidden returned no layer - the client cannot snapshot the '
        'rebuilt geometry and undo will restore the stale one')
    returned = {(p['row'], p['col']): p for p in body['layer']['panels']}
    assert returned[(0, 1)]['hidden'] is True
    # Geometry in the RESPONSE already reflects the re-anchor.
    assert returned[(1, 1)]['y'] == 192
    assert returned[(1, 1)]['height'] == 64
    # And it matches what the server itself now holds.
    assert body['layer'] == _get_project(client)['layers'][0]


def test_toggle_panel_hidden_returns_rebuilt_layer(client):
    layer_id, by_rc = _screen_with_half_and_neighbour(client)
    resp = client.post(
        f'/api/layer/{layer_id}/panel/{by_rc[(0, 1)]}/toggle_hidden')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    # Layer-shaped, not panel-shaped: the old panel object is stale once the
    # panels array is regenerated.
    assert body.get('id') == layer_id
    assert isinstance(body.get('panels'), list) and len(body['panels']) == 9
    returned = {(p['row'], p['col']): p for p in body['panels']}
    assert returned[(0, 1)]['hidden'] is True
    assert returned[(1, 1)]['y'] == 192
    assert body == _get_project(client)['layers'][0]


def test_set_panels_hidden_layer_survives_a_restore_unchanged(client):
    """End to end: what the route hands the client is what a PUT gives back,
    so the client's history snapshot cannot disagree with the server."""
    layer_id, by_rc = _screen_with_half_and_neighbour(client, 'width')
    resp = client.post(f'/api/layer/{layer_id}/panels/set_hidden',
                       json={'panels': [{'id': by_rc[(1, 0)], 'hidden': True}]})
    snapshot = resp.get_json()['layer']['panels']
    assert _panels_of(_put(client, _get_project(client))) == snapshot


# ── 1c. rows/columns are authoritative - out-of-grid panel state is dropped ─

def test_restore_regenerates_panels_to_match_rows_columns(client):
    """The rebuild trusts rows/columns over the panels array. A layer whose
    panels array disagrees loses the surplus panels (and their hidden / blank /
    halfTile state) outright - worth knowing before any future code path lets
    rows/columns drift from panels."""
    project = _stale_half_row_project(rows=3, columns=4)
    layer = project['layers'][0]
    layer['rows'] = 2
    layer['columns'] = 2
    for p in layer['panels']:
        p['hidden'] = p['row'] == 2  # state that only exists outside the grid
    restored = _put(client, project)
    panels = _panels_of(restored)
    assert len(panels) == 4
    assert all(p['hidden'] is False for p in panels)


def test_restore_backfills_missing_panels_for_the_declared_grid(client):
    project = {'name': 'B', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 4, 'rows': 3,
         'cabinet_width': 100, 'cabinet_height': 100,
         'offset_x': 0, 'offset_y': 0, 'panels': []}]}
    assert len(_panels_of(_put(client, project))) == 12


def test_full_half_row_collapses_and_reflows(client):
    """Sanity anchor for the idempotency tests: the collapse actually happens."""
    project = _scenario_full_half_row(client)
    panels = _panels_of(_put(client, project))
    by_rc = {(p['row'], p['col']): p for p in panels}
    assert by_rc[(1, 0)]['height'] == 64
    assert by_rc[(1, 0)]['y'] == 128
    assert by_rc[(2, 0)]['y'] == 192  # reflowed up by the collapsed row
    assert by_rc[(2, 0)]['height'] == 128


# ── 2. SELF-HEALING ───────────────────────────────────────────────────────

def _stale_half_row_project(rows=3, columns=4, cw=128, ch=128):
    """A project exactly as the pre-v0.10.8 bulk half-tile path left it:
    halfTile='height' stamped on every panel of row 0, but the geometry still
    full size and the rows below NOT reflowed."""
    panels = []
    n = 1
    for r in range(rows):
        for c in range(columns):
            panels.append({
                'id': n, 'number': n, 'row': r, 'col': c,
                'x': c * cw, 'y': r * ch, 'width': cw, 'height': ch,
                'blank': False, 'hidden': False,
                'halfTile': 'height' if r == 0 else 'none',
                'is_color1': (r + c) % 2 == 0,
            })
            n += 1
    return {
        'name': 'Stale', 'raster_width': 1920, 'raster_height': 1080,
        'layers': [{
            'id': 1, 'type': 'screen', 'name': 'Stale', 'visible': True,
            'columns': columns, 'rows': rows,
            'cabinet_width': cw, 'cabinet_height': ch,
            'offset_x': 0, 'offset_y': 0,
            'panels': panels,
        }],
    }


def test_restore_heals_stale_bulk_half_tile_geometry(client):
    project = _stale_half_row_project()
    restored = _put(client, project)
    by_rc = {(p['row'], p['col']): p for p in _panels_of(restored)}
    # Row 0 collapsed to half height, still at the top.
    for c in range(4):
        assert by_rc[(0, c)]['height'] == 64, f'row0 col{c} not collapsed'
        assert by_rc[(0, c)]['y'] == 0
        assert by_rc[(0, c)]['width'] == 128
    # Rows below reflowed up.
    for c in range(4):
        assert by_rc[(1, c)]['y'] == 64
        assert by_rc[(2, c)]['y'] == 192


def test_healed_geometry_is_then_stable(client):
    """Healing once must not keep healing (i.e. the fix converges)."""
    _assert_idempotent(client, _stale_half_row_project(), 'stale-heal')


def test_restore_heals_stale_half_width_column(client):
    project = _stale_half_row_project()
    layer = project['layers'][0]
    for p in layer['panels']:
        p['halfTile'] = 'width' if p['col'] == 0 else 'none'
    restored = _put(client, project)
    by_rc = {(p['row'], p['col']): p for p in _panels_of(restored)}
    for r in range(3):
        assert by_rc[(r, 0)]['width'] == 64
        assert by_rc[(r, 0)]['x'] == 0
        assert by_rc[(r, 1)]['x'] == 64  # reflowed left


# ── 3. NON-SCREEN LAYERS UNTOUCHED ────────────────────────────────────────

def test_image_and_text_layers_round_trip_unchanged(client):
    img = client.post('/api/layer/add-image', json={
        'name': 'Logo', 'imageData': 'data:image/png;base64,AAAA',
        'imageWidth': 400, 'imageHeight': 200,
        'offset_x': 10, 'offset_y': 20, 'imageScale': 1.5,
    }).get_json()
    txt = client.post('/api/layer/add-text', json={
        'name': 'Note', 'textContent': 'hello', 'offset_x': 30,
        'offset_y': 40, 'textWidth': 300, 'textHeight': 80,
        'fontSize': 18,
    }).get_json()
    _add_screen(client, 'Wall', columns=2, rows=2)

    project = _get_project(client)
    restored = _put(client, project)
    by_id = {l['id']: l for l in restored['layers']}

    for original in (img, txt):
        got = by_id[original['id']]
        # No field dropped, no value silently changed.
        for key, value in original.items():
            if key in ('showOffsetX', 'showOffsetY'):
                continue  # legitimately backfilled by restore_project
            assert key in got, f'{original["type"]} layer lost field {key!r}'
            assert got[key] == value, (
                f'{original["type"]} layer field {key!r} changed: '
                f'{value!r} -> {got[key]!r}'
            )
        # The rebuild must not invent panels for a non-screen layer.
        assert got.get('panels') == [], (
            f'{original["type"]} layer gained panels: {got.get("panels")!r}'
        )


def test_text_layer_without_panels_key_gains_none(client):
    project = {
        'name': 'T', 'layers': [
            {'id': 1, 'type': 'text', 'name': 'Note', 'textContent': 'x',
             'offset_x': 0, 'offset_y': 0},
            {'id': 2, 'type': 'image', 'name': 'Img', 'imageData': '',
             'offset_x': 0, 'offset_y': 0},
        ],
    }
    restored = _put(client, project)
    for layer in restored['layers']:
        assert 'panels' not in layer, (
            f"{layer['type']} layer had a 'panels' key invented: {layer!r}")


def test_unknown_layer_type_is_left_alone(client):
    project = {
        'name': 'X', 'layers': [
            {'id': 1, 'type': 'group', 'name': 'Weird', 'foo': 'bar'},
        ],
    }
    restored = _put(client, project)
    assert restored['layers'][0]['foo'] == 'bar'
    assert 'panels' not in restored['layers'][0]


# ── 4. LEGACY HALF FLAGS ──────────────────────────────────────────────────

def _legacy_project(rows=3, columns=4, cw=128, ch=128, **flags):
    """Pre-per-panel-state file: layer-level half flags, panels carry no
    halfTile at all, geometry is whatever the old build produced (full size)."""
    panels = []
    n = 1
    for r in range(rows):
        for c in range(columns):
            panels.append({
                'id': n, 'number': n, 'row': r, 'col': c,
                'x': c * cw, 'y': r * ch, 'width': cw, 'height': ch,
                'blank': False, 'hidden': False,
                'is_color1': (r + c) % 2 == 0,
            })
            n += 1
    layer = {
        'id': 1, 'type': 'screen', 'name': 'Legacy', 'visible': True,
        'columns': columns, 'rows': rows,
        'cabinet_width': cw, 'cabinet_height': ch,
        'offset_x': 0, 'offset_y': 0,
        'halfFirstColumn': False, 'halfLastColumn': False,
        'halfFirstRow': False, 'halfLastRow': False,
        'panels': panels,
    }
    layer.update(flags)
    return {'name': 'LegacyProj', 'layers': [layer]}


def test_legacy_half_first_row_migrates(client):
    restored = _put(client, _legacy_project(halfFirstRow=True))
    layer = restored['layers'][0]
    by_rc = {(p['row'], p['col']): p for p in layer['panels']}
    for c in range(4):
        assert by_rc[(0, c)]['halfTile'] == 'height'
        assert by_rc[(0, c)]['height'] == 64
        assert by_rc[(1, c)]['y'] == 64
    assert layer['halfFirstRow'] is False, 'legacy flag not cleared'


def test_legacy_half_last_column_migrates(client):
    restored = _put(client, _legacy_project(halfLastColumn=True))
    by_rc = {(p['row'], p['col']): p for p in _panels_of(restored)}
    for r in range(3):
        assert by_rc[(r, 3)]['halfTile'] == 'width'
        assert by_rc[(r, 3)]['width'] == 64
        assert by_rc[(r, 3)]['x'] == 3 * 128


@pytest.mark.parametrize('flags', [
    {'halfFirstRow': True},
    {'halfLastRow': True},
    {'halfFirstColumn': True},
    {'halfLastColumn': True},
    {'halfFirstRow': True, 'halfLastRow': True},
    {'halfFirstColumn': True, 'halfLastColumn': True},
    {'halfFirstRow': True, 'halfFirstColumn': True},
    {'halfFirstRow': True, 'halfLastRow': True,
     'halfFirstColumn': True, 'halfLastColumn': True},
])
def test_legacy_flags_do_not_double_apply_on_repeat_restore(client, flags):
    """Highest-risk interaction: the migration is one-way and MUTATES the
    layer. Restoring the migrated result again must not shrink anything
    further, nor drift."""
    _assert_idempotent(client, _legacy_project(**flags), f'legacy {flags}')


def test_legacy_flags_on_single_row_single_column(client):
    """halfFirstRow and halfLastRow both address row 0 on a 1x1 grid."""
    _assert_idempotent(
        client,
        _legacy_project(rows=1, columns=1, halfFirstRow=True,
                        halfLastRow=True, halfFirstColumn=True,
                        halfLastColumn=True),
        'legacy 1x1 all flags')


def test_legacy_flag_does_not_override_existing_per_panel_half(client):
    """A panel that already carries halfTile='width' must keep it when a
    legacy row flag also covers it."""
    project = _legacy_project(halfFirstRow=True)
    for p in project['layers'][0]['panels']:
        if p['row'] == 0 and p['col'] == 1:
            p['halfTile'] = 'width'
    restored = _put(client, project)
    by_rc = {(p['row'], p['col']): p for p in _panels_of(restored)}
    assert by_rc[(0, 1)]['halfTile'] == 'width'
    assert by_rc[(0, 0)]['halfTile'] == 'height'
    # Row 0 is now MIXED, so it must NOT collapse.
    assert by_rc[(1, 0)]['y'] == 128
    _assert_idempotent(client, project, 'legacy + existing half')


def test_stale_legacy_flag_reapplies_half_tiles_the_user_removed(client):
    """DEFECT PROBE.

    Sequence a real user can hit: a project still carrying halfFirstRow=True
    (a file saved by an older build, or a client whose in-memory layer still
    has the flag set because the server cleared it only on ITS copy), where
    the user has since set those panels back to halfTile='none'.

    On restore the migration sees the flag still True and the panel state
    'none', so it re-stamps halfTile='height' across the row: undo/file-load
    silently resurrects half-tiles the user deleted.
    """
    project = _legacy_project(halfFirstRow=True)
    # User explicitly cleared the half-tiles on row 0.
    for p in project['layers'][0]['panels']:
        p['halfTile'] = 'none'
    restored = _put(client, project)
    by_rc = {(p['row'], p['col']): p for p in _panels_of(restored)}
    resurrected = [rc for rc, p in by_rc.items()
                   if rc[0] == 0 and p['halfTile'] == 'height']
    # Documenting current behaviour. The migration is unconditional on the
    # flag, so it wins over the explicit per-panel 'none'.
    assert resurrected, (
        'behaviour changed: legacy flag no longer overrides explicit '
        "halfTile='none' - update this test")
    # It must at least be stable afterwards.
    _assert_idempotent(client, project, 'stale legacy flag')


def test_legacy_screen_layer_without_type_key_is_rebuilt(client):
    """Layers from before the 'type' field exist without it, and the rest of
    the app treats a missing type as 'screen' (app.py uses
    ``(l.get('type') or 'screen') == 'screen'``). v0.10.8.1 made
    restore_project match, so these self-heal instead of being skipped."""
    project = _legacy_project(halfFirstRow=True)
    del project['layers'][0]['type']
    restored = _put(client, project)
    layer = restored['layers'][0]
    by_rc = {(p['row'], p['col']): p for p in layer['panels']}
    for c in range(4):
        assert by_rc[(0, c)]['halfTile'] == 'height'
        assert by_rc[(0, c)]['height'] == 64
        assert by_rc[(1, c)]['y'] == 64
    assert layer['halfFirstRow'] is False, 'legacy flag not cleared'
    # Still no 'type' invented, and still converges.
    assert 'type' not in layer
    _assert_idempotent(client, project, 'type-less legacy screen')


# ── 5. EDGE CASES - none may 500 ──────────────────────────────────────────

EDGE_CASES = {
    'no_layers_key': {'name': 'E'},
    'empty_layers': {'name': 'E', 'layers': []},
    'screen_without_panels_key': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 3, 'rows': 2,
         'cabinet_width': 100, 'cabinet_height': 100,
         'offset_x': 0, 'offset_y': 0}]},
    'zero_rows': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 4, 'rows': 0,
         'cabinet_width': 100, 'cabinet_height': 100, 'panels': []}]},
    'zero_columns': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 0, 'rows': 4,
         'cabinet_width': 100, 'cabinet_height': 100, 'panels': []}]},
    'zero_both': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 0, 'rows': 0,
         'cabinet_width': 100, 'cabinet_height': 100, 'panels': []}]},
    'missing_cabinet_size': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 2, 'rows': 2,
         'panels': []}]},
    'null_cabinet_size': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 2, 'rows': 2,
         'cabinet_width': None, 'cabinet_height': None, 'panels': []}]},
    'string_dimensions': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': '3', 'rows': '2',
         'cabinet_width': '100', 'cabinet_height': '100', 'panels': []}]},
    'negative_rows': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 2, 'rows': -3,
         'cabinet_width': 100, 'cabinet_height': 100, 'panels': []}]},
    'panels_none': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 2, 'rows': 2,
         'cabinet_width': 100, 'cabinet_height': 100, 'panels': None}]},
    'null_entry_in_panels': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 2, 'rows': 2,
         'cabinet_width': 100, 'cabinet_height': 100,
         'panels': [None, {'id': 2, 'row': 0, 'col': 1}]}]},
    'panels_missing_row_col': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 2, 'rows': 2,
         'cabinet_width': 100, 'cabinet_height': 100,
         'panels': [{'id': 1}, {'id': 2}]}]},
    'panel_row_out_of_range': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 2, 'rows': 2,
         'cabinet_width': 100, 'cabinet_height': 100,
         'panels': [{'id': 1, 'row': 99, 'col': 99, 'halfTile': 'height'}]}]},
    'bogus_half_tile_value': {'name': 'E', 'layers': [
        {'id': 1, 'type': 'screen', 'name': 'S', 'columns': 2, 'rows': 2,
         'cabinet_width': 100, 'cabinet_height': 100,
         'panels': [{'id': 1, 'row': 0, 'col': 0, 'halfTile': 'diagonal'}]}]},
}


# ``panels_none`` (the key present but null) used to die with a TypeError ->
# HTTP 500, because `_rebuild_layer_geometry_from_panel_states` did
#   for p in layer.get('panels', [])
# and a .get default only applies when the key is MISSING. Fixed in v0.10.8.1
# with `for p in (layer.get('panels') or [])`. Kept in the table because a 500
# here means undo / redo / file load fails outright for that project.
@pytest.mark.parametrize('name', sorted(EDGE_CASES))
def test_edge_cases_do_not_500(client, name):
    resp = client.put('/api/project', json=EDGE_CASES[name])
    assert resp.status_code == 200, (
        f'{name}: PUT /api/project returned {resp.status_code}\n'
        f'{resp.get_data(as_text=True)[:2000]}')


@pytest.mark.parametrize('name', sorted(EDGE_CASES))
def test_edge_cases_are_idempotent(client, name):
    _assert_idempotent(client, EDGE_CASES[name], name)


def test_null_panels_survives_with_and_without_the_rebuild(client, monkeypatch):
    """Pin both sides of the fixed regression: a null ``panels`` is fine with
    the rebuild in place, and was fine before it existed. If someone
    reintroduces the `.get('panels', [])` form, the first assert catches it."""
    payload = EDGE_CASES['panels_none']
    assert client.put('/api/project', json=payload).status_code == 200
    # The layer is rebuilt into a real 2x2 grid, not left as null.
    assert len(_panels_of(_get_project(client))) == 4
    monkeypatch.setattr(
        app_module, '_rebuild_layer_geometry_from_panel_states',
        lambda layer: None)
    assert client.put('/api/project', json=payload).status_code == 200


def test_zero_row_screen_produces_no_panels(client):
    restored = _put(client, EDGE_CASES['zero_rows'])
    assert _panels_of(restored) == []


def test_bogus_half_tile_value_is_normalised(client):
    restored = _put(client, EDGE_CASES['bogus_half_tile_value'])
    assert all(p['halfTile'] == 'none' for p in _panels_of(restored))


def test_empty_body_does_not_500(client):
    resp = client.put('/api/project', json={})
    assert resp.status_code == 200


# ── 6. COST OF THE REBUILD ────────────────────────────────────────────────

def _build_large_project(client, screen_count=34, big_cols=14, big_rows=11):
    """34 screen layers, the first with 154 panels, the rest 8x5."""
    _add_screen(client, 'Big', columns=big_cols, rows=big_rows,
                cw=128, ch=128)
    for i in range(screen_count - 1):
        _add_screen(client, f'S{i}', columns=8, rows=5, cw=128, ch=128,
                    offset_x=i * 100, offset_y=i * 50)
    project = _get_project(client)
    assert len(project['layers']) == screen_count
    assert len(project['layers'][0]['panels']) == big_cols * big_rows
    return project


def _median_put_ms(client, project, reps=9):
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter()
        resp = client.put('/api/project', json=project)
        samples.append((time.perf_counter() - t0) * 1000.0)
        assert resp.status_code == 200
    samples.sort()
    return samples[len(samples) // 2]


def test_rebuild_cost_on_large_project(client, monkeypatch, capsys):
    project = _build_large_project(client)
    total_panels = sum(len(l['panels']) for l in project['layers'])

    with_rebuild = _median_put_ms(client, project)

    real = app_module._rebuild_layer_geometry_from_panel_states
    monkeypatch.setattr(
        app_module, '_rebuild_layer_geometry_from_panel_states',
        lambda layer: None)
    without_rebuild = _median_put_ms(client, project)
    monkeypatch.setattr(
        app_module, '_rebuild_layer_geometry_from_panel_states', real)

    delta = with_rebuild - without_rebuild
    with capsys.disabled():
        print(
            f'\n[rebuild cost] {len(project["layers"])} screen layers, '
            f'{total_panels} panels total (largest {len(project["layers"][0]["panels"])})\n'
            f'  PUT with rebuild:    {with_rebuild:7.2f} ms\n'
            f'  PUT without rebuild: {without_rebuild:7.2f} ms\n'
            f'  rebuild delta:       {delta:7.2f} ms'
        )
    # Undo has to stay snappy. Generous ceiling so CI noise cannot flake it;
    # the printed number is the thing to watch.
    assert delta < 150, (
        f'geometry rebuild adds {delta:.1f} ms to every undo/redo - '
        f'that is too slow')


def test_large_project_restore_is_idempotent(client):
    """The realistic project must also survive repeated undo without drift."""
    project = _build_large_project(client, screen_count=6)
    _assert_idempotent(client, project, 'large project')
