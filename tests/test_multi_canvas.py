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
