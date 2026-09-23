"""Tests for v0.8 multi-canvas data model + migrator (Slice 1).

Slice 1 is *additive backend only*: the project file format gains a
``canvases`` array, ``format_version``, ``active_canvas_id``; layers gain
``canvas_id``; v0.7 projects auto-migrate on load. The client is unchanged
in this slice, so root-level raster fields must still be preserved.
"""


def _v07_project():
    """Build a representative v0.7-format project (no canvases / format_version)."""
    return {
        'name': 'Legacy Show',
        'raster_width': 11520,
        'raster_height': 2272,
        'show_raster_width': 11520,
        'show_raster_height': 2272,
        'data_flow_perspective': 'front',
        'power_perspective': 'back',
        'layers': [
            {
                'id': 1, 'type': 'screen', 'name': 'SR',
                'offset_x': 0, 'offset_y': 0,
                'showOffsetX': 0, 'showOffsetY': 0,
                'columns': 4, 'rows': 3,
                'cabinet_width': 128, 'cabinet_height': 128,
                'panels': [],
            },
            {
                'id': 2, 'type': 'screen', 'name': 'SL',
                'offset_x': 1024, 'offset_y': 0,
                'showOffsetX': 1024, 'showOffsetY': 0,
                'columns': 4, 'rows': 3,
                'cabinet_width': 128, 'cabinet_height': 128,
                'panels': [],
            },
        ],
    }


def test_migrate_v07_project_creates_default_canvas(client):
    """A v0.7 project loaded via PUT gains canvases + canvas_id on every layer."""
    project = _v07_project()
    resp = client.put('/api/project', json=project)
    assert resp.status_code == 200
    data = resp.get_json()

    assert data['format_version'] == '0.8'
    assert isinstance(data['canvases'], list) and len(data['canvases']) == 1
    canvas = data['canvases'][0]
    assert canvas['id'] == 'c1'
    assert canvas['name'] == 'Canvas 1'
    assert canvas['raster_width'] == 11520
    assert canvas['raster_height'] == 2272
    assert canvas['show_raster_width'] == 11520
    assert canvas['show_raster_height'] == 2272
    assert canvas['data_flow_perspective'] == 'front'
    assert canvas['power_perspective'] == 'back'
    assert canvas['workspace_x'] == 0 and canvas['workspace_y'] == 0
    assert canvas['visible'] is True
    assert canvas['color']  # palette colour present

    assert data['active_canvas_id'] == 'c1'
    assert all(layer['canvas_id'] == 'c1' for layer in data['layers'])


def test_migrate_preserves_root_fields(client):
    """Slice 1 is additive, root raster/perspective fields must remain."""
    project = _v07_project()
    resp = client.put('/api/project', json=project)
    assert resp.status_code == 200
    data = resp.get_json()

    # Root-level fields the existing single-canvas client still reads.
    assert data['raster_width'] == 11520
    assert data['raster_height'] == 2272
    assert data['show_raster_width'] == 11520
    assert data['show_raster_height'] == 2272
    assert data['data_flow_perspective'] == 'front'
    assert data['power_perspective'] == 'back'


def test_migrate_idempotent(client):
    """Loading an already-v0.8 project must not duplicate canvases."""
    project = _v07_project()
    # First load: migrates.
    first = client.put('/api/project', json=project).get_json()
    assert first['format_version'] == '0.8'
    assert len(first['canvases']) == 1
    canvases_after_first = first['canvases']

    # Second load of the (now-v0.8) project: no-op.
    second = client.put('/api/project', json=first).get_json()
    assert second['format_version'] == '0.8'
    assert len(second['canvases']) == 1
    assert second['canvases'] == canvases_after_first
    assert second['active_canvas_id'] == 'c1'


def test_new_project_has_one_canvas(client_with_layer):
    """POST /api/project/new returns a v0.8 project with one canvas + default layer."""
    resp = client_with_layer.post('/api/project/new')
    assert resp.status_code == 200
    data = resp.get_json()

    assert data['format_version'] == '0.8'
    assert len(data['canvases']) == 1
    canvas = data['canvases'][0]
    assert canvas['id'] == 'c1'
    assert data['active_canvas_id'] == 'c1'

    # Default layer assigned to the canvas.
    assert len(data['layers']) == 1
    assert data['layers'][0]['canvas_id'] == 'c1'


def test_add_layer_assigns_canvas_id(client):
    """POST /api/layer/add stamps the new layer with the active canvas id."""
    project_resp = client.get('/api/project').get_json()
    expected_canvas_id = project_resp['active_canvas_id']
    assert expected_canvas_id  # sanity

    resp = client.post('/api/layer/add', json={
        'name': 'NewScreen',
        'columns': 2, 'rows': 2,
        'cabinet_width': 128, 'cabinet_height': 128,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['canvas_id'] == expected_canvas_id


def test_round_trip_preserves_canvases(client):
    """Save then restore a multi-canvas project; canvases array survives intact."""
    project = _v07_project()
    # Migrate first.
    migrated = client.put('/api/project', json=project).get_json()

    # Hand-craft a second canvas to verify multi-canvas round-trips work.
    migrated['canvases'].append({
        'id': 'c2',
        'name': 'Canvas 2',
        'color': '#F5A623',
        'workspace_x': 5000,
        'workspace_y': 0,
        'raster_width': 1920,
        'raster_height': 1080,
        'show_raster_width': 1920,
        'show_raster_height': 1080,
        'data_flow_perspective': 'front',
        'power_perspective': 'front',
        'visible': True,
    })
    migrated['active_canvas_id'] = 'c2'

    # Round-trip via save then restore.
    save_resp = client.post('/api/project', json=migrated)
    assert save_resp.status_code == 200
    restored = client.put('/api/project', json=migrated).get_json()

    assert len(restored['canvases']) == 2
    assert restored['canvases'][1]['id'] == 'c2'
    assert restored['canvases'][1]['workspace_x'] == 5000
    assert restored['active_canvas_id'] == 'c2'
    assert restored['format_version'] == '0.8'
    # Layers unchanged.
    assert all(l['canvas_id'] == 'c1' for l in restored['layers'])


def test_refuse_newer_format_version(client):
    """Loading a project authored by a newer app version returns 400."""
    project = _v07_project()
    project['format_version'] = '0.9'
    resp = client.put('/api/project', json=project)
    assert resp.status_code == 400
    body = resp.get_json()
    assert 'newer' in body['error'].lower()
    assert '0.9' in body['error']


# -----------------------------------------------------------------------------
# Slice 2, canvas CRUD endpoints.
# -----------------------------------------------------------------------------


def test_create_canvas_appends_and_activates(client):
    """POST /api/canvas appends a new canvas and makes it active."""
    resp = client.post('/api/canvas', json={})
    assert resp.status_code == 200
    proj = resp.get_json()
    assert len(proj['canvases']) == 2
    new_canvas = proj['canvases'][1]
    assert new_canvas['id'] == 'c2'
    assert new_canvas['name'] == 'Canvas 2'
    assert new_canvas['visible'] is True
    assert proj['active_canvas_id'] == 'c2'
    # Color should be different from canvas 1 (auto-cycled).
    assert new_canvas['color'] != proj['canvases'][0]['color']


def test_create_canvas_skips_used_colors(client):
    """Auto-cycled color skips colors already in use."""
    # First canvas uses palette[0]. Force it to palette[1] manually so the
    # next auto-pick should land on palette[0] (the first unused one).
    from app import DEFAULT_CANVAS_PALETTE
    client.put('/api/canvas/c1', json={'color': DEFAULT_CANVAS_PALETTE[1]})
    resp = client.post('/api/canvas', json={})
    proj = resp.get_json()
    assert proj['canvases'][1]['color'] == DEFAULT_CANVAS_PALETTE[0]


def test_delete_canvas_refuses_last(client):
    """Cannot delete the final remaining canvas."""
    resp = client.delete('/api/canvas/c1')
    assert resp.status_code == 400
    body = resp.get_json()
    assert 'last' in body['error'].lower()


def test_delete_canvas_removes_layers(client_with_layer):
    """Deleting a canvas removes all of that canvas's layers and reassigns active."""
    # Add a second canvas, then move/add layers there.
    client_with_layer.post('/api/canvas', json={})  # c2
    # The default layer is on c1; verify it.
    proj = client_with_layer.get('/api/project').get_json()
    assert proj['layers'][0]['canvas_id'] == 'c1'
    assert proj['active_canvas_id'] == 'c2'  # newly added is active

    # Delete c1, should remove its layer and reassign active to c2.
    resp = client_with_layer.delete('/api/canvas/c1')
    assert resp.status_code == 200
    proj = resp.get_json()
    assert len(proj['canvases']) == 1
    assert proj['canvases'][0]['id'] == 'c2'
    assert proj['active_canvas_id'] == 'c2'
    assert all(l['canvas_id'] == 'c2' for l in proj['layers'])
    # The c1 layer is gone.
    assert len(proj['layers']) == 0


def test_duplicate_canvas_clones_layers(client_with_layer):
    """Duplicating a canvas clones its layers with fresh layer ids."""
    proj = client_with_layer.get('/api/project').get_json()
    src_layer_id = proj['layers'][0]['id']

    resp = client_with_layer.post('/api/canvas/c1/duplicate')
    assert resp.status_code == 200
    proj = resp.get_json()
    assert len(proj['canvases']) == 2
    new_canvas = proj['canvases'][1]
    assert new_canvas['id'] == 'c2'
    # v0.8: smart name iteration. "Canvas 1" + dup → "Canvas 2".
    assert new_canvas['name'] == 'Canvas 2'
    assert proj['active_canvas_id'] == 'c2'
    # Should now have two layers, original on c1, clone on c2 with new id.
    assert len(proj['layers']) == 2
    cloned = [l for l in proj['layers'] if l['canvas_id'] == 'c2']
    assert len(cloned) == 1
    assert cloned[0]['id'] != src_layer_id


def test_reorder_canvases(client):
    """POST /api/canvas/reorder reorders the canvases array."""
    client.post('/api/canvas', json={})  # c2
    client.post('/api/canvas', json={})  # c3
    resp = client.post('/api/canvas/reorder', json={
        'canvas_ids': ['c3', 'c1', 'c2']
    })
    assert resp.status_code == 200
    proj = resp.get_json()
    assert [c['id'] for c in proj['canvases']] == ['c3', 'c1', 'c2']


def test_reorder_rejects_mismatched_ids(client):
    """Reorder with an unknown id returns 400."""
    resp = client.post('/api/canvas/reorder', json={'canvas_ids': ['c1', 'cX']})
    assert resp.status_code == 400


def test_set_active_canvas(client):
    """PUT /api/canvas/<id>/active updates active_canvas_id."""
    client.post('/api/canvas', json={})  # c2 (now active)
    resp = client.put('/api/canvas/c1/active')
    assert resp.status_code == 200
    proj = resp.get_json()
    assert proj['active_canvas_id'] == 'c1'


def test_move_layer_to_canvas_keeps_offsets(client_with_layer):
    """Moving a layer to another canvas KEEPS its position.

    This asserted a reset to 0,0 (design Section 5.7) until Matt asked for the
    opposite: canvases share a coordinate space, so a screen that moves should
    land where it already was instead of jumping to the corner and needing to
    be dragged back by eye. See tests/test_canvas_move_keeps_position.py.
    """
    proj = client_with_layer.get('/api/project').get_json()
    layer_id = proj['layers'][0]['id']
    # Set a non-zero offset so we can verify the reset.
    client_with_layer.put(f'/api/layer/{layer_id}', json={
        'offset_x': 500, 'offset_y': 300,
        'showOffsetX': 500, 'showOffsetY': 300,
    })
    client_with_layer.post('/api/canvas', json={})  # c2

    resp = client_with_layer.put(f'/api/layer/{layer_id}/canvas', json={
        'canvas_id': 'c2', 'mode': 'move',
    })
    assert resp.status_code == 200
    proj = resp.get_json()
    moved = next(l for l in proj['layers'] if l['id'] == layer_id)
    assert moved['canvas_id'] == 'c2'
    assert moved['offset_x'] == 500 and moved['offset_y'] == 300
    assert moved['showOffsetX'] == 500 and moved['showOffsetY'] == 300


def test_duplicate_layer_to_canvas(client_with_layer):
    """Duplicate mode creates a copy with a new id, keeping the source position."""
    proj = client_with_layer.get('/api/project').get_json()
    src_layer_id = proj['layers'][0]['id']
    src_name = proj['layers'][0]['name']
    client_with_layer.post('/api/canvas', json={})  # c2

    resp = client_with_layer.put(f'/api/layer/{src_layer_id}/canvas', json={
        'canvas_id': 'c2', 'mode': 'duplicate',
    })
    assert resp.status_code == 200
    proj = resp.get_json()
    assert len(proj['layers']) == 2
    src_still_there = next(l for l in proj['layers'] if l['id'] == src_layer_id)
    assert src_still_there['canvas_id'] == 'c1'
    clone = next(l for l in proj['layers'] if l['id'] != src_layer_id)
    assert clone['canvas_id'] == 'c2'
    assert clone['name'] == src_name
    assert clone['offset_x'] == 0 and clone['offset_y'] == 0


def test_duplicate_layer_to_canvas_keeps_clone_offsets(client_with_layer):
    """Slice 7: duplicate-to-canvas drops the clone at 0,0 even when the
    source has non-zero offsets. The cross-canvas drag relies on this
    server-side guarantee so the clone always lands at the new canvas's
    top-left, regardless of where the user dropped it.
    """
    proj = client_with_layer.get('/api/project').get_json()
    src_id = proj['layers'][0]['id']
    client_with_layer.put(f'/api/layer/{src_id}', json={
        'offset_x': 777, 'offset_y': 555,
        'showOffsetX': 999, 'showOffsetY': 111,
    })
    client_with_layer.post('/api/canvas', json={})  # c2

    resp = client_with_layer.put(f'/api/layer/{src_id}/canvas', json={
        'canvas_id': 'c2', 'mode': 'duplicate',
    })
    assert resp.status_code == 200
    proj = resp.get_json()
    clone = next(l for l in proj['layers'] if l['id'] != src_id)
    assert clone['canvas_id'] == 'c2'
    # Keeps the source position - same reason as the move case above.
    assert clone['offset_x'] == 777 and clone['offset_y'] == 555
    assert clone['showOffsetX'] == 999 and clone['showOffsetY'] == 111
    # Source untouched
    src = next(l for l in proj['layers'] if l['id'] == src_id)
    assert src['offset_x'] == 777 and src['offset_y'] == 555


def test_move_layer_to_unknown_canvas_404(client_with_layer):
    """Moving to a non-existent canvas returns 404."""
    proj = client_with_layer.get('/api/project').get_json()
    layer_id = proj['layers'][0]['id']
    resp = client_with_layer.put(f'/api/layer/{layer_id}/canvas', json={
        'canvas_id': 'cX', 'mode': 'move',
    })
    assert resp.status_code == 404


def test_update_canvas_partial(client):
    """PUT /api/canvas/<id> applies a partial update."""
    resp = client.put('/api/canvas/c1', json={
        'name': 'Main Stage', 'visible': False,
    })
    assert resp.status_code == 200
    proj = resp.get_json()
    assert proj['canvases'][0]['name'] == 'Main Stage'
    assert proj['canvases'][0]['visible'] is False


def test_update_canvas_persists_workspace_position(client):
    """Slice 5: workspace_x / workspace_y written by canvas-drag drop persist."""
    resp = client.put('/api/canvas/c1', json={
        'workspace_x': 1234, 'workspace_y': -56,
    })
    assert resp.status_code == 200
    proj = resp.get_json()
    assert proj['canvases'][0]['workspace_x'] == 1234
    assert proj['canvases'][0]['workspace_y'] == -56


# -----------------------------------------------------------------------------
# Slice 3, auto-place new canvases horizontally with a configurable gap.
# -----------------------------------------------------------------------------

# v0.8 Slice 9: default canvas gap dropped 50 -> 0. Most LED installs are
# abutting walls, not floating screens. The canvasGap preference still
# overrides this when set (test_canvas_gap_preference covers that path).
DEFAULT_CANVAS_GAP = 0


def test_new_canvas_auto_placed_to_right(client):
    """A second canvas is placed at workspace_x = first_canvas.raster_width + gap."""
    import app as app_module
    app_module.server_preferences = {}
    proj = client.get('/api/project').get_json()
    first = proj['canvases'][0]
    expected_x = (first['workspace_x'] or 0) + first['raster_width'] + DEFAULT_CANVAS_GAP

    resp = client.post('/api/canvas', json={})
    assert resp.status_code == 200
    proj = resp.get_json()
    new_canvas = proj['canvases'][1]
    assert new_canvas['workspace_x'] == expected_x
    assert new_canvas['workspace_y'] == 0


def test_canvas_gap_preference(client):
    """Setting canvasGap via /api/preferences changes the auto-placement gap."""
    import app as app_module
    app_module.server_preferences = {}
    client.put('/api/preferences', json={'canvasGap': 200})
    proj = client.get('/api/project').get_json()
    first = proj['canvases'][0]
    expected_x = (first['workspace_x'] or 0) + first['raster_width'] + 200

    resp = client.post('/api/canvas', json={})
    proj = resp.get_json()
    assert proj['canvases'][1]['workspace_x'] == expected_x


def test_duplicated_canvas_auto_placed(client_with_layer):
    """Duplicating a canvas places the duplicate to the right with the gap."""
    import app as app_module
    app_module.server_preferences = {}
    proj = client_with_layer.get('/api/project').get_json()
    first = proj['canvases'][0]
    expected_x = (first['workspace_x'] or 0) + first['raster_width'] + DEFAULT_CANVAS_GAP

    resp = client_with_layer.post('/api/canvas/c1/duplicate')
    assert resp.status_code == 200
    proj = resp.get_json()
    dup = proj['canvases'][1]
    assert dup['workspace_x'] == expected_x
    assert dup['workspace_y'] == 0


def test_active_canvas_id_round_trips_on_save_load(client):
    """Slice 4: active_canvas_id survives a save/load round-trip so when
    the user reopens a project the canvas they had selected is still
    active (toolbar raster + sidebar highlight + workspace tint all
    follow it). Frontend selection paths set active_canvas_id; this
    verifies the persistence half of that contract."""
    # Add a second canvas and make it active.
    client.post('/api/canvas', json={})  # creates c2, sets it active
    resp = client.put('/api/canvas/c2/active')
    assert resp.status_code == 200
    proj_before = resp.get_json()
    assert proj_before['active_canvas_id'] == 'c2'

    # Save, then reload.
    save = client.post('/api/project', json=proj_before)
    assert save.status_code == 200
    restored = client.put('/api/project', json=proj_before).get_json()

    assert restored['active_canvas_id'] == 'c2'
    assert [c['id'] for c in restored['canvases']] == ['c1', 'c2']


def test_set_active_does_not_drop_layers(client_with_layer):
    """Slice 5: switching the active canvas must not delete or reassign
    any layers. The selection-strip behaviour (clearing cross-canvas
    selected layer ids) lives on the client; the server's job is purely
    to record the new active_canvas_id and return the project unchanged.
    Guards against future refactors that might over-eagerly prune layers."""
    proj = client_with_layer.get('/api/project').get_json()
    layer_ids_before = sorted(l['id'] for l in proj['layers'])
    layer_canvases_before = {l['id']: l['canvas_id'] for l in proj['layers']}

    # Add a second canvas (auto-activates) then switch back to c1.
    client_with_layer.post('/api/canvas', json={})  # c2, now active
    resp = client_with_layer.put('/api/canvas/c1/active')
    assert resp.status_code == 200
    after = resp.get_json()

    assert after['active_canvas_id'] == 'c1'
    layer_ids_after = sorted(l['id'] for l in after['layers'])
    layer_canvases_after = {l['id']: l['canvas_id'] for l in after['layers']}
    assert layer_ids_before == layer_ids_after
    assert layer_canvases_before == layer_canvases_after


def test_active_canvas_selection_scoping_rule_documented():
    """Slice 5 design rule (frontend-only, documented here for future devs):

    When the active canvas changes, the client clears any selected layer
    ids that don't belong to the new active canvas, and demotes
    currentLayer if it's no longer in-scope. This is implemented in
    ``setActiveCanvas`` in src/static/js/app.js. Together with Slice 4's
    ``_activateCanvasForLayer`` (called from selectLayer /
    toggleLayerSelection / selectLayerRange), the invariant is:

        currentLayer.canvas_id === project.active_canvas_id

    after every layer selection or canvas activation. If you remove the
    scoping logic, update this test deliberately.
    """
    # Marker assertion; the real verification is the manual UX checklist
    # (no headless browser in CI).
    assert True


def test_duplicate_canvas_name_iterates_trailing_number(client_with_layer):
    """Duplicating "Canvas 1" yields "Canvas 2" (next free trailing number)."""
    r = client_with_layer.post('/api/canvas/c1/duplicate')
    assert r.status_code == 200
    p = r.get_json()
    names = [c['name'] for c in p['canvases']]
    assert names == ['Canvas 1', 'Canvas 2']
    # Duplicating again → "Canvas 3"
    r = client_with_layer.post('/api/canvas/c2/duplicate')
    p = r.get_json()
    names = [c['name'] for c in p['canvases']]
    assert names == ['Canvas 1', 'Canvas 2', 'Canvas 3']


def test_duplicate_canvas_name_appends_1_when_no_suffix(client_with_layer):
    """Duplicating a custom-named canvas like "EDC" yields "EDC 1"."""
    client_with_layer.put('/api/canvas/c1', json={'name': 'EDC'})
    r = client_with_layer.post('/api/canvas/c1/duplicate')
    p = r.get_json()
    names = [c['name'] for c in p['canvases']]
    assert names == ['EDC', 'EDC 1']
    # And again → "EDC 2"
    r = client_with_layer.post('/api/canvas/c2/duplicate')
    p = r.get_json()
    names = [c['name'] for c in p['canvases']]
    assert names == ['EDC', 'EDC 1', 'EDC 2']


# -----------------------------------------------------------------------------
# Slice 6, per-canvas raster (toolbar source-of-truth on active canvas).
# -----------------------------------------------------------------------------


def test_toolbar_raster_change_only_touches_active_canvas(client):
    """PUT /api/canvas/<id> with raster_* changes ONLY that canvas; siblings
    keep their own raster sizes (per-canvas raster is now real)."""
    # Two canvases, each with its own initial raster.
    client.put('/api/canvas/c1', json={'raster_width': 1920, 'raster_height': 1080})
    client.post('/api/canvas', json={})  # c2 (auto-cloned from active = c1)
    client.put('/api/canvas/c2', json={'raster_width': 800, 'raster_height': 600})

    # Activate c1 and "edit the toolbar" via the canvas update endpoint,
    # mimics the Slice 6 client which routes the toolbar change to the
    # active canvas, not to project root.
    client.put('/api/canvas/c1/active')
    resp = client.put('/api/canvas/c1', json={
        'raster_width': 11520, 'raster_height': 2272,
        'show_raster_width': 11520, 'show_raster_height': 2272,
    })
    assert resp.status_code == 200
    proj = resp.get_json()
    by_id = {c['id']: c for c in proj['canvases']}

    # c1 picked up the change.
    assert by_id['c1']['raster_width'] == 11520
    assert by_id['c1']['raster_height'] == 2272
    # c2 is untouched.
    assert by_id['c2']['raster_width'] == 800
    assert by_id['c2']['raster_height'] == 600


def test_root_raster_mirrors_active_canvas(client):
    """Backwards-compat shim: project root raster_* mirrors the active
    canvas's raster on every save/update response."""
    client.post('/api/canvas', json={})  # c2 (active)
    client.put('/api/canvas/c2', json={'raster_width': 4096, 'raster_height': 2160})

    proj = client.get('/api/project').get_json()
    # Active is c2 → root mirrors c2's raster.
    assert proj['active_canvas_id'] == 'c2'
    assert proj['raster_width'] == 4096
    assert proj['raster_height'] == 2160

    # Switch active to c1 → root remirrors to c1's raster.
    client.put('/api/canvas/c1/active')
    # Trigger a refresh by hitting the project endpoint.
    proj = client.get('/api/project').get_json()
    # GET /api/project does not re-mirror (it just returns current_project),
    # but set_active_canvas uses socketio_emit; either way we want any state-
    # changing call to leave root in sync. Prove this by issuing a no-op
    # canvas update on c1 and inspecting the response.
    resp = client.put('/api/canvas/c1', json={})
    proj = resp.get_json()
    by_id = {c['id']: c for c in proj['canvases']}
    assert proj['raster_width'] == by_id['c1']['raster_width']
    assert proj['raster_height'] == by_id['c1']['raster_height']


def test_save_project_with_root_raster_propagates_to_active_canvas(client):
    """Backwards-compat: a POST /api/project that sends only root-level
    raster_* (no canvases payload) flows through to the active canvas so
    older clients/tests still drive raster size from the toolbar."""
    proj_before = client.get('/api/project').get_json()
    active_id = proj_before['active_canvas_id']

    client.post('/api/project', json={
        'raster_width': 7680,
        'raster_height': 4320,
    })

    proj = client.get('/api/project').get_json()
    by_id = {c['id']: c for c in proj['canvases']}
    assert by_id[active_id]['raster_width'] == 7680
    assert by_id[active_id]['raster_height'] == 4320
    # Root is mirrored.
    assert proj['raster_width'] == 7680
    assert proj['raster_height'] == 4320


def test_set_active_canvas_changes_what_toolbar_reads(client):
    """Switching active canvas updates the project-root raster mirror so the
    toolbar (which reflects whichever canvas is active) shows the new
    values. Mirrors a typical setActiveCanvas → syncRasterFromProject flow."""
    # c1 has 1920x1080 by default. Add c2 with a different raster.
    client.post('/api/canvas', json={})  # c2 active
    client.put('/api/canvas/c2', json={'raster_width': 3840, 'raster_height': 2160})
    proj = client.get('/api/project').get_json()
    assert proj['active_canvas_id'] == 'c2'
    assert proj['raster_width'] == 3840

    # Switch active to c1.
    client.put('/api/canvas/c1/active')
    # A subsequent canvas update (or any state-changing call) re-mirrors:
    proj = client.put('/api/canvas/c1', json={}).get_json()
    by_id = {c['id']: c for c in proj['canvases']}
    assert proj['raster_width'] == by_id['c1']['raster_width']
    # And the original c2 raster is untouched.
    assert by_id['c2']['raster_width'] == 3840


def test_per_canvas_raster_round_trips(client):
    """Save / restore a multi-canvas project; each canvas's per-view raster
    sizes survive intact (Slice 6 prerequisite for per-view per-canvas)."""
    proj = client.get('/api/project').get_json()
    proj['canvases'].append({
        'id': 'c2', 'name': 'C2', 'color': '#F5A623',
        'workspace_x': 5000, 'workspace_y': 0,
        'raster_width': 1280, 'raster_height': 720,
        'show_raster_width': 2560, 'show_raster_height': 1440,
        'data_flow_perspective': 'front',
        'power_perspective': 'front',
        'visible': True,
    })
    proj['active_canvas_id'] = 'c2'
    restored = client.put('/api/project', json=proj).get_json()
    by_id = {c['id']: c for c in restored['canvases']}
    assert by_id['c2']['raster_width'] == 1280
    assert by_id['c2']['raster_height'] == 720
    assert by_id['c2']['show_raster_width'] == 2560
    assert by_id['c2']['show_raster_height'] == 1440
    # And the c1 default raster is preserved (independent of c2's).
    assert by_id['c1']['raster_width'] != by_id['c2']['raster_width']


def _add_screen_on(client, canvas_id):
    """Create a screen on ``canvas_id`` and return its id."""
    resp = client.post('/api/layer/add', json={
        'name': 'Screen on ' + canvas_id, 'columns': 2, 'rows': 2,
        'cabinet_width': 128, 'cabinet_height': 128, 'canvas_id': canvas_id,
    })
    assert resp.status_code == 200, resp.get_json()
    layer = resp.get_json()
    assert layer['canvas_id'] == canvas_id, layer
    return layer['id']


def test_delete_canvas_keeps_screens_shown_elsewhere(client_with_layer):
    """Issue 112: a screen dragged to another canvas on Show Look / Data /
    Power only changes where it is SHOWN (show_canvas_id); its home canvas
    (canvas_id) stays. Deleting the home used to delete the screen even
    though the user could see it on the other canvas. It moves house instead."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    proj = c.get('/api/project').get_json()
    layer_id = proj['layers'][0]['id']
    assert proj['layers'][0]['canvas_id'] == 'c1'
    # Show Look drag onto c2.
    resp = c.put(f'/api/layer/{layer_id}/show_canvas', json={'show_canvas_id': 'c2'})
    assert resp.status_code == 200
    resp = c.delete('/api/canvas/c1')
    assert resp.status_code == 200
    proj = resp.get_json()
    assert [cv['id'] for cv in proj['canvases']] == ['c2']
    survivors = [l for l in proj['layers'] if l['id'] == layer_id]
    assert len(survivors) == 1, 'the screen shown on c2 must survive c1 being deleted'
    assert survivors[0]['canvas_id'] == 'c2'
    # Home and show canvas now agree, so the override is cleared.
    assert survivors[0].get('show_canvas_id') in (None, '')
    assert proj['active_canvas_id'] == 'c2'


def test_delete_canvas_still_removes_screens_with_no_other_home(client_with_layer):
    """A screen shown on the deleted canvas itself, or on no other canvas,
    goes with the canvas as before."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    proj = c.get('/api/project').get_json()
    layer_id = proj['layers'][0]['id']
    # Explicitly shown on its own canvas: no other home.
    c.put(f'/api/layer/{layer_id}/show_canvas', json={'show_canvas_id': 'c1'})
    proj = c.delete('/api/canvas/c1').get_json()
    assert all(l['id'] != layer_id for l in proj['layers'])


def test_delete_canvas_clears_show_override_pointing_at_it(client_with_layer):
    """The reverse case: a screen whose home survives but which was shown on
    the deleted canvas falls back to its home, instead of pointing at a
    canvas that no longer exists (which hid it on every show view)."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    proj = c.get('/api/project').get_json()
    layer_id = proj['layers'][0]['id']  # home c1
    c.put(f'/api/layer/{layer_id}/show_canvas', json={'show_canvas_id': 'c2'})
    proj = c.delete('/api/canvas/c2').get_json()
    layer = next(l for l in proj['layers'] if l['id'] == layer_id)
    assert layer['canvas_id'] == 'c1'
    assert layer.get('show_canvas_id') in (None, '')


def test_delete_canvas_rehomed_group_stays_a_group(client_with_layer):
    """Two grouped screens both shown on c2 move house together and stay
    grouped; a member whose partner was deleted with the canvas leaves the
    group (which then dissolves)."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    proj = c.get('/api/project').get_json()
    a = proj['layers'][0]['id']
    import app as app_module
    app_module.current_project['active_canvas_id'] = 'c1'
    b = _add_screen_on(c, 'c1')
    # Groups are made client-side and saved with the project; set one up
    # straight in the server model the way a saved project would carry it.
    app_module.current_project['groups'] = [{'id': 'g1', 'name': 'Wall', 'layer_ids': [a, b]}]
    for l in app_module.current_project['layers']:
        if l['id'] in (a, b):
            l['group_id'] = 'g1'
    for lid in (a, b):
        c.put(f'/api/layer/{lid}/show_canvas', json={'show_canvas_id': 'c2'})
    proj = c.delete('/api/canvas/c1').get_json()
    by_id = {l['id']: l for l in proj['layers']}
    assert a in by_id and b in by_id
    assert by_id[a]['canvas_id'] == by_id[b]['canvas_id'] == 'c2'
    groups = proj.get('groups') or []
    member_sets = [set(g.get('layer_ids') or []) for g in groups]
    assert {a, b} in member_sets, (groups, by_id[a].get('group_id'))


def _group_on_server(ids, gid='g1'):
    """Put ``ids`` in one group straight in the server model, the way a saved
    project carries it (groups are made client-side)."""
    import app as app_module
    app_module.current_project['groups'] = [{'id': gid, 'name': 'Wall', 'layer_ids': list(ids)}]
    for l in app_module.current_project['layers']:
        if l['id'] in ids:
            l['group_id'] = gid


def _member_sets(proj):
    return [set(g.get('layer_ids') or []) for g in (proj.get('groups') or [])]


def test_delete_canvas_group_survives_a_member_deleted_with_the_canvas(client_with_layer):
    """Repro A: a, b, c grouped on c1; a and b shown on c2; delete c1. The
    membership used to be settled one re-homed layer at a time in layer
    order, so a (first) saw c still listed with no layer behind it and
    dropped out, and the group dissolved. {a, b} must stay a group on c2."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    import app as app_module
    app_module.current_project['active_canvas_id'] = 'c1'
    a = c.get('/api/project').get_json()['layers'][0]['id']
    b = _add_screen_on(c, 'c1')
    cc = _add_screen_on(c, 'c1')
    _group_on_server([a, b, cc])
    for lid in (a, b):
        c.put(f'/api/layer/{lid}/show_canvas', json={'show_canvas_id': 'c2'})
    proj = c.delete('/api/canvas/c1').get_json()
    by_id = {l['id']: l for l in proj['layers']}
    assert cc not in by_id, 'c had nowhere else to go'
    assert by_id[a]['canvas_id'] == by_id[b]['canvas_id'] == 'c2'
    assert {a, b} in _member_sets(proj), (proj.get('groups'), by_id[a].get('group_id'))
    assert by_id[a]['group_id'] == by_id[b]['group_id'] == 'g1'


def test_delete_canvas_group_keeps_the_members_that_moved_together(client_with_layer):
    """Repro B: a, b shown on c2 and c shown on c3; delete c1. Settled per
    layer, a saw b still on c1 (not yet re-homed) and left; settled per
    group, {a, b} on c2 is the larger partition and stays, c is ungrouped."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    c.post('/api/canvas', json={})  # c3
    import app as app_module
    app_module.current_project['active_canvas_id'] = 'c1'
    a = c.get('/api/project').get_json()['layers'][0]['id']
    b = _add_screen_on(c, 'c1')
    cc = _add_screen_on(c, 'c1')
    _group_on_server([a, b, cc])
    for lid in (a, b):
        c.put(f'/api/layer/{lid}/show_canvas', json={'show_canvas_id': 'c2'})
    c.put(f'/api/layer/{cc}/show_canvas', json={'show_canvas_id': 'c3'})
    proj = c.delete('/api/canvas/c1').get_json()
    by_id = {l['id']: l for l in proj['layers']}
    assert by_id[a]['canvas_id'] == by_id[b]['canvas_id'] == 'c2'
    assert by_id[cc]['canvas_id'] == 'c3'
    assert _member_sets(proj) == [{a, b}], proj.get('groups')
    assert by_id[cc].get('group_id') is None
    assert by_id[a]['group_id'] == by_id[b]['group_id'] == 'g1'


def test_delete_canvas_group_tie_keeps_the_earliest_members_canvas(client_with_layer):
    """Two partitions of equal size: the one holding the earliest member in
    layer_ids stays the group. a, b -> c2 and c, d -> c3, with the group
    listing d, c, b, a: {c, d} on c3 holds the earliest member (d)."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    c.post('/api/canvas', json={})  # c3
    import app as app_module
    app_module.current_project['active_canvas_id'] = 'c1'
    a = c.get('/api/project').get_json()['layers'][0]['id']
    b = _add_screen_on(c, 'c1')
    cc = _add_screen_on(c, 'c1')
    d = _add_screen_on(c, 'c1')
    _group_on_server([d, cc, b, a])
    for lid in (a, b):
        c.put(f'/api/layer/{lid}/show_canvas', json={'show_canvas_id': 'c2'})
    for lid in (cc, d):
        c.put(f'/api/layer/{lid}/show_canvas', json={'show_canvas_id': 'c3'})
    proj = c.delete('/api/canvas/c1').get_json()
    by_id = {l['id']: l for l in proj['layers']}
    assert _member_sets(proj) == [{cc, d}], proj.get('groups')
    assert by_id[cc]['group_id'] == by_id[d]['group_id'] == 'g1'
    assert by_id[a].get('group_id') is None and by_id[b].get('group_id') is None


def test_delete_canvas_group_tie_is_by_member_order_not_canvas_id(client_with_layer):
    """Same layout as the tie test with the natural a, b, c, d order: the c2
    pair holds the earliest member (a) and stays."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    c.post('/api/canvas', json={})  # c3
    import app as app_module
    app_module.current_project['active_canvas_id'] = 'c1'
    a = c.get('/api/project').get_json()['layers'][0]['id']
    b = _add_screen_on(c, 'c1')
    cc = _add_screen_on(c, 'c1')
    d = _add_screen_on(c, 'c1')
    _group_on_server([a, b, cc, d])
    for lid in (a, b):
        c.put(f'/api/layer/{lid}/show_canvas', json={'show_canvas_id': 'c2'})
    for lid in (cc, d):
        c.put(f'/api/layer/{lid}/show_canvas', json={'show_canvas_id': 'c3'})
    proj = c.delete('/api/canvas/c1').get_json()
    assert _member_sets(proj) == [{a, b}], proj.get('groups')


def test_move_layer_to_canvas_still_detaches_a_single_mover(client_with_layer):
    """_detach_from_cross_canvas_group keeps its behaviour for the move
    route: one member moved to another canvas leaves its group."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    import app as app_module
    app_module.current_project['active_canvas_id'] = 'c1'
    a = c.get('/api/project').get_json()['layers'][0]['id']
    b = _add_screen_on(c, 'c1')
    cc = _add_screen_on(c, 'c1')
    _group_on_server([a, b, cc])
    proj = c.put(f'/api/layer/{a}/canvas', json={'canvas_id': 'c2', 'mode': 'move'}).get_json()
    by_id = {l['id']: l for l in proj['layers']}
    assert by_id[a]['canvas_id'] == 'c2' and by_id[a].get('group_id') is None
    assert _member_sets(proj) == [{b, cc}], proj.get('groups')


def test_delete_canvas_rehomes_a_layer_with_an_unhashable_id(client_with_layer):
    """A hand-edited layer whose id is a dict, shown on c2, is re-homed when
    c1 goes. _regroup_rehomed_layers put every re-homed id in a set without
    the _is_hashable guard by_id uses, so the delete came back 500. Such an
    id can never match a group's layer_ids entry and is treated like any id
    that names nothing."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    import app as app_module
    app_module.current_project['active_canvas_id'] = 'c1'
    a = c.get('/api/project').get_json()['layers'][0]['id']
    b = _add_screen_on(c, 'c1')
    _group_on_server([a, b])
    for lid in (a, b):
        c.put(f'/api/layer/{lid}/show_canvas', json={'show_canvas_id': 'c2'})
    odd = {
        'id': {'not': 'an id'}, 'type': 'screen', 'name': 'Odd',
        'canvas_id': 'c1', 'show_canvas_id': 'c2',
        'offset_x': 0, 'offset_y': 0, 'columns': 1, 'rows': 1,
        'cabinet_width': 128, 'cabinet_height': 128, 'panels': [],
    }
    app_module.current_project['layers'].append(odd)
    resp = c.delete('/api/canvas/c1')
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    proj = resp.get_json()
    homes = [l['canvas_id'] for l in proj['layers']]
    assert homes == ['c2'] * 3, proj['layers']
    assert {a, b} in _member_sets(proj), proj.get('groups')
    assert odd['group_id'] is None if 'group_id' in odd else True


def test_delete_canvas_regroup_ignores_a_duplicated_member_id(client_with_layer):
    """A group listing [a, a, b, c] with a -> c2 and b, c -> c3: counted as
    written, a's canvas held two entries and tied with {b, c}, and the tie
    rule kept a (the earliest) - the real pair was ungrouped. The ids are
    deduped before partitioning, so {b, c} is the larger side and stays."""
    c = client_with_layer
    c.post('/api/canvas', json={})  # c2
    c.post('/api/canvas', json={})  # c3
    import app as app_module
    app_module.current_project['active_canvas_id'] = 'c1'
    a = c.get('/api/project').get_json()['layers'][0]['id']
    b = _add_screen_on(c, 'c1')
    cc = _add_screen_on(c, 'c1')
    _group_on_server([a, a, b, cc])
    c.put(f'/api/layer/{a}/show_canvas', json={'show_canvas_id': 'c2'})
    for lid in (b, cc):
        c.put(f'/api/layer/{lid}/show_canvas', json={'show_canvas_id': 'c3'})
    proj = c.delete('/api/canvas/c1').get_json()
    by_id = {l['id']: l for l in proj['layers']}
    assert _member_sets(proj) == [{b, cc}], proj.get('groups')
    assert by_id[a].get('group_id') is None
    assert by_id[b]['group_id'] == by_id[cc]['group_id'] == 'g1'
    assert proj['groups'][0]['layer_ids'] == [b, cc]
