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
    """Slice 1 is additive — root raster/perspective fields must remain."""
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
# Slice 2 — canvas CRUD endpoints.
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

    # Delete c1 — should remove its layer and reassign active to c2.
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
    # Should now have two layers — original on c1, clone on c2 with new id.
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


def test_move_layer_to_canvas_resets_offsets(client_with_layer):
    """Moving a layer to another canvas resets its offsets to 0,0."""
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
    assert moved['offset_x'] == 0 and moved['offset_y'] == 0
    assert moved['showOffsetX'] == 0 and moved['showOffsetY'] == 0


def test_duplicate_layer_to_canvas(client_with_layer):
    """Duplicate mode creates a copy with a new id at 0,0 in the target canvas."""
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
# Slice 3 — auto-place new canvases horizontally with a configurable gap.
# -----------------------------------------------------------------------------

DEFAULT_CANVAS_GAP = 50


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

    after every layer selection or canvas activation. This test is a
    documentation anchor — if you remove the scoping logic, please update
    docs/multi-canvas-design.md and delete this assertion deliberately.
    """
    # Marker assertion; the real verification is the manual UX checklist
    # in the slice 5 PR description (no headless browser in CI).
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
