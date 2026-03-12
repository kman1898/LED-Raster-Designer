"""Advanced layer tests: cabinet resize state preservation, image layers,
visibility, locking, multi-layer interactions, and optional field pass-through."""


def test_cabinet_resize_preserves_blank_state(client):
    """Changing cabinet size regenerates panels but preserves blank state."""
    resp = client.post('/api/layer/add', json={
        'name': 'Resize',
        'columns': 3,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 100,
    })
    layer = resp.get_json()
    layer_id = layer['id']
    panel_id = layer['panels'][0]['id']

    # Blank the first panel
    client.post(f'/api/layer/{layer_id}/panel/{panel_id}/toggle')

    # Change cabinet size (triggers panel regeneration)
    resp = client.put(f'/api/layer/{layer_id}', json={'cabinet_width': 200})
    updated = resp.get_json()
    assert updated['cabinet_width'] == 200
    # Panel state should be preserved via old_panel_states
    first_panel = updated['panels'][0]
    assert first_panel['blank'] is True


def test_cabinet_resize_preserves_hidden_state(client):
    """Changing rows/cols preserves hidden state on matching panel IDs."""
    resp = client.post('/api/layer/add', json={
        'name': 'HideResize',
        'columns': 3,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 100,
    })
    layer = resp.get_json()
    layer_id = layer['id']
    panel_id = layer['panels'][0]['id']

    # Hide first panel
    client.post(f'/api/layer/{layer_id}/panel/{panel_id}/toggle_hidden')

    # Change rows (triggers regeneration)
    resp = client.put(f'/api/layer/{layer_id}', json={'rows': 3})
    updated = resp.get_json()
    assert len(updated['panels']) == 9  # 3x3
    assert updated['panels'][0]['hidden'] is True


def test_update_layer_visibility(client_with_layer):
    """Setting visible=False on a layer is stored correctly."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={'visible': False})
    assert resp.status_code == 200
    assert resp.get_json()['visible'] is False

    # Toggle back
    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={'visible': True})
    assert resp.get_json()['visible'] is True


def test_update_layer_locked(client_with_layer):
    """Setting locked=True on a layer is stored."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={'locked': True})
    assert resp.status_code == 200
    assert resp.get_json()['locked'] is True


def test_update_image_layer_scale(client):
    """Image layer scale can be updated."""
    resp = client.post('/api/layer/add-image', json={
        'name': 'Logo',
        'imageData': 'data:image/png;base64,iVBORw==',
        'imageWidth': 200,
        'imageHeight': 100,
        'imageScale': 1.0,
    })
    layer = resp.get_json()

    resp = client.put(f'/api/layer/{layer["id"]}', json={'imageScale': 0.5})
    assert resp.status_code == 200
    assert resp.get_json()['imageScale'] == 0.5


def test_update_image_layer_position(client):
    """Image layer offset can be updated without triggering panel regen."""
    resp = client.post('/api/layer/add-image', json={
        'name': 'Logo',
        'imageData': 'data:image/png;base64,iVBORw==',
        'imageWidth': 200,
        'imageHeight': 100,
    })
    layer = resp.get_json()

    resp = client.put(f'/api/layer/{layer["id"]}', json={
        'offset_x': 50,
        'offset_y': 75,
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['offset_x'] == 50
    assert updated['offset_y'] == 75


def test_multiple_layers_independent(client):
    """Multiple layers maintain independent state."""
    resp1 = client.post('/api/layer/add', json={
        'name': 'Screen1', 'columns': 2, 'rows': 2,
        'cabinet_width': 100, 'cabinet_height': 100,
    })
    resp2 = client.post('/api/layer/add', json={
        'name': 'Screen2', 'columns': 4, 'rows': 3,
        'cabinet_width': 50, 'cabinet_height': 50,
    })
    layer1 = resp1.get_json()
    layer2 = resp2.get_json()

    # Modify layer1
    client.put(f'/api/layer/{layer1["id"]}', json={'name': 'Modified'})

    # layer2 should be unchanged
    project = client.get('/api/project').get_json()
    l2 = next(l for l in project['layers'] if l['id'] == layer2['id'])
    assert l2['name'] == 'Screen2'
    assert l2['columns'] == 4


def test_delete_one_of_multiple_layers(client):
    """Deleting one layer doesn't affect the other."""
    resp1 = client.post('/api/layer/add', json={'name': 'Keep'})
    resp2 = client.post('/api/layer/add', json={'name': 'Delete'})
    keep_id = resp1.get_json()['id']
    delete_id = resp2.get_json()['id']

    client.delete(f'/api/layer/{delete_id}')

    project = client.get('/api/project').get_json()
    assert len(project['layers']) == 1
    assert project['layers'][0]['id'] == keep_id
    assert project['layers'][0]['name'] == 'Keep'


def test_add_layer_with_optional_colors(client):
    """Layer creation accepts optional color fields."""
    resp = client.post('/api/layer/add', json={
        'name': 'Colored',
        'columns': 2,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 100,
        'color1': '#FF0000',
        'color2': '#00FF00',
        'border_color': '#0000FF',
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['color1'] == '#FF0000'
    assert layer['color2'] == '#00FF00'
    assert layer['border_color'] == '#0000FF'


def test_add_layer_with_data_flow_settings(client):
    """Layer creation accepts data flow pattern settings."""
    resp = client.post('/api/layer/add', json={
        'name': 'DataFlow',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
        'dataFlowPattern': 'horizontal-right',
        'arrowColor': '#FFFFFF',
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['dataFlowPattern'] == 'horizontal-right'
    assert layer['arrowColor'] == '#FFFFFF'


def test_add_layer_with_power_settings(client):
    """Layer creation accepts power configuration."""
    resp = client.post('/api/layer/add', json={
        'name': 'Power',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
        'powerVoltage': '110',
        'panelWatts': 150,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['powerVoltage'] == '110'
    assert layer['panelWatts'] == 150


def test_update_layer_cabinet_id_style(client_with_layer):
    """Cabinet ID display settings can be updated."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'cabinetIdStyle': 'A1',
        'cabinetIdPosition': 'center',
        'cabinetIdColor': '#FFFF00',
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['cabinetIdStyle'] == 'A1'
    assert layer['cabinetIdPosition'] == 'center'


def test_offset_only_change_shifts_panels(client):
    """Changing only offset shifts panels without regenerating."""
    resp = client.post('/api/layer/add', json={
        'name': 'Shift',
        'columns': 2,
        'rows': 1,
        'cabinet_width': 100,
        'cabinet_height': 100,
        'offset_x': 0,
        'offset_y': 0,
    })
    layer = resp.get_json()
    original_count = len(layer['panels'])
    original_ids = [p['id'] for p in layer['panels']]

    resp = client.put(f'/api/layer/{layer["id"]}', json={
        'offset_x': 50,
        'offset_y': 25,
    })
    updated = resp.get_json()
    # Same number of panels, same IDs (not regenerated)
    assert len(updated['panels']) == original_count
    new_ids = [p['id'] for p in updated['panels']]
    assert new_ids == original_ids
    # Positions shifted
    assert updated['panels'][0]['x'] == 50
    assert updated['panels'][0]['y'] == 25


def test_project_full_round_trip(client):
    """Save and restore a full project with layers, then verify."""
    # Add two layers
    client.post('/api/layer/add', json={
        'name': 'Screen1', 'columns': 4, 'rows': 3,
        'cabinet_width': 128, 'cabinet_height': 128,
    })
    client.post('/api/layer/add', json={
        'name': 'Screen2', 'columns': 2, 'rows': 2,
        'cabinet_width': 64, 'cabinet_height': 64,
    })

    # Get full project state
    project = client.get('/api/project').get_json()
    assert len(project['layers']) == 2

    # Restore it via PUT
    resp = client.put('/api/project', json=project)
    assert resp.status_code == 200
    restored = resp.get_json()
    assert len(restored['layers']) == 2
    assert restored['layers'][0]['name'] == 'Screen1'
    assert restored['layers'][1]['name'] == 'Screen2'
