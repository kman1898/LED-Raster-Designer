"""Tests for layer management API endpoints."""

import json


def test_add_layer(client):
    """POST /api/layer/add creates a new screen layer with panels."""
    resp = client.post('/api/layer/add', json={
        'name': 'MainScreen',
        'columns': 8,
        'rows': 5,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['name'] == 'MainScreen'
    assert layer['columns'] == 8
    assert layer['rows'] == 5
    assert layer['cabinet_width'] == 128
    assert len(layer['panels']) == 40  # 8 * 5


def test_add_layer_default_values(client):
    """Adding a layer without specifying all fields uses defaults."""
    resp = client.post('/api/layer/add', json={'name': 'Minimal'})
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['columns'] == 8
    assert layer['rows'] == 5


def test_add_layer_generates_unique_ids(client):
    """Each added layer gets a unique incrementing ID."""
    resp1 = client.post('/api/layer/add', json={'name': 'Screen1'})
    resp2 = client.post('/api/layer/add', json={'name': 'Screen2'})
    id1 = resp1.get_json()['id']
    id2 = resp2.get_json()['id']
    assert id1 != id2
    assert id2 > id1


def test_add_image_layer(client):
    """POST /api/layer/add-image creates an image layer."""
    resp = client.post('/api/layer/add-image', json={
        'name': 'Logo',
        'imageData': 'data:image/png;base64,iVBORw==',
        'imageWidth': 200,
        'imageHeight': 100,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['type'] == 'image'
    assert layer['name'] == 'Logo'
    assert layer['imageWidth'] == 200


def test_update_layer_name(client_with_layer):
    """PUT /api/layer/<id> updates layer properties."""
    # Get the layer ID
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'name': 'RenamedScreen',
    })
    assert resp.status_code == 200
    assert resp.get_json()['name'] == 'RenamedScreen'


def test_update_layer_resizes_panels(client_with_layer):
    """Changing columns/rows regenerates panels."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'columns': 6,
        'rows': 4,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert len(layer['panels']) == 24  # 6 * 4


def test_update_layer_offset_shifts_panels(client_with_layer):
    """Changing offset shifts panel positions without regenerating."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']
    original_panels = project['layers'][0]['panels']
    original_x = original_panels[0]['x']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'offset_x': 100,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    # Panel x should have shifted by 100
    assert layer['panels'][0]['x'] == original_x + 100


def test_update_nonexistent_layer(client):
    """Updating a layer that doesn't exist returns 404."""
    resp = client.put('/api/layer/9999', json={'name': 'Ghost'})
    assert resp.status_code == 404


def test_delete_layer(client_with_layer):
    """DELETE /api/layer/<id> removes the layer."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.delete(f'/api/layer/{layer_id}')
    assert resp.status_code == 200

    project = client_with_layer.get('/api/project').get_json()
    assert len(project['layers']) == 0


def test_half_panel_dimensions(client):
    """Legacy halfFirstColumn / halfLastRow flags migrate to per-panel
    halfTile state, producing the same visual result.

    Note: under the new per-panel model, a corner panel can only be half
    in one dimension at a time (height OR width, not both). The migration
    gives row-based half flags precedence, so a corner cell affected by
    both halfFirstColumn and halfLastRow becomes half-HEIGHT (the row flag
    wins). Non-overlapping cells get exactly the dimension they were
    flagged for.
    """
    resp = client.post('/api/layer/add', json={
        'name': 'HalfTest',
        'columns': 3,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 100,
    })
    assert resp.status_code == 200
    layer_id = resp.get_json()['id']

    resp = client.put(f'/api/layer/{layer_id}', json={
        'halfFirstColumn': True,
        'halfLastRow': True,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    panels = layer['panels']

    # First column panels (excluding the corner that the row flag claims)
    # should have width 50.
    first_col_non_overlap = [p for p in panels if p['col'] == 0 and p['row'] != 1]
    for p in first_col_non_overlap:
        assert p['width'] == 50

    # Last row panels should all have height 50.
    last_row_panels = [p for p in panels if p['row'] == 1]
    for p in last_row_panels:
        assert p['height'] == 50


def test_duplicate_layer_with_hidden_panels(client):
    """Duplicating a layer preserves hidden panel state."""
    # Add a layer
    resp = client.post('/api/layer/add', json={
        'name': 'Original',
        'columns': 3,
        'rows': 2,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()

    # Duplicate with hidden panels
    resp = client.post('/api/layer/add', json={
        'name': 'Duplicate',
        'columns': 3,
        'rows': 2,
        'cabinet_width': 128,
        'cabinet_height': 128,
        'hiddenPanels': [{'row': 0, 'col': 0}, {'row': 1, 'col': 2}],
    })
    assert resp.status_code == 200
    dup = resp.get_json()
    hidden = [p for p in dup['panels'] if p['hidden']]
    assert len(hidden) == 2


def test_duplicate_layer_with_half_rows_builds_correct_panels(client):
    """Duplicating a layer with halfFirstRow should produce half-height panels
    in the first row immediately, without requiring a subsequent update."""
    resp = client.post('/api/layer/add', json={
        'name': 'HalfRowDup',
        'columns': 3,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 100,
        'halfFirstRow': True,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    first_row = [p for p in layer['panels'] if p['row'] == 0]
    second_row = [p for p in layer['panels'] if p['row'] == 1]
    # First row should be half height
    for p in first_row:
        assert p['height'] == 50, f"First row panel height should be 50, got {p['height']}"
    # Second row should be full height
    for p in second_row:
        assert p['height'] == 100, f"Second row panel height should be 100, got {p['height']}"


def test_duplicate_layer_with_half_columns_builds_correct_panels(client):
    """Duplicating a layer with halfFirstColumn and halfLastColumn should
    produce half-width panels in first and last columns immediately."""
    resp = client.post('/api/layer/add', json={
        'name': 'HalfColDup',
        'columns': 4,
        'rows': 2,
        'cabinet_width': 120,
        'cabinet_height': 80,
        'halfFirstColumn': True,
        'halfLastColumn': True,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    first_col = [p for p in layer['panels'] if p['col'] == 0]
    last_col = [p for p in layer['panels'] if p['col'] == 3]
    middle_col = [p for p in layer['panels'] if p['col'] == 1]
    for p in first_col:
        assert p['width'] == 60, f"First col panel width should be 60, got {p['width']}"
    for p in last_col:
        assert p['width'] == 60, f"Last col panel width should be 60, got {p['width']}"
    for p in middle_col:
        assert p['width'] == 120, f"Middle col panel width should be 120, got {p['width']}"


def test_duplicate_layer_preserves_data_label_properties(client):
    """Duplicating a layer should preserve data tab label properties
    (portLabelTemplatePrimary, portLabelTemplateReturn, etc.)."""
    resp = client.post('/api/layer/add', json={
        'name': 'LabelSource',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
        'portLabelTemplatePrimary': 'OUT#',
        'portLabelTemplateReturn': 'IN#',
        'portLabelOverridesPrimary': {'1': 'MainOut', '2': 'AuxOut'},
        'portLabelOverridesReturn': {'1': 'MainIn'},
        'showDataFlowPortInfo': True,
        'customPortPaths': {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}]},
        'customPortIndex': 2,
        'randomDataColors': True,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['portLabelTemplatePrimary'] == 'OUT#'
    assert layer['portLabelTemplateReturn'] == 'IN#'
    assert layer['portLabelOverridesPrimary'] == {'1': 'MainOut', '2': 'AuxOut'}
    assert layer['portLabelOverridesReturn'] == {'1': 'MainIn'}
    assert layer['showDataFlowPortInfo'] is True
    assert layer['customPortPaths'] == {'1': [{'row': 0, 'col': 0}, {'row': 0, 'col': 1}]}
    assert layer['customPortIndex'] == 2
    assert layer['randomDataColors'] is True
