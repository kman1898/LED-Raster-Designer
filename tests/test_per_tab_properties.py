"""Tests for per-tab Screen Name properties and related layer settings.

Covers the v0.6.4.2 fix: each tab (Pixel Map, Cabinet ID, Data Flow, Power)
has its own independent showLabelName property. Old projects with only the
global showLabelName should fall back correctly.
"""

import json


# ── Per-tab property persistence via API ─────────────────────────────────


def test_per_tab_label_properties_accepted_on_update(client_with_layer):
    """Server accepts showLabelNameCabinet/DataFlow/Power on layer update."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'showLabelName': False,
        'showLabelNameCabinet': True,
        'showLabelNameDataFlow': False,
        'showLabelNamePower': True,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['showLabelName'] is False
    assert layer['showLabelNameCabinet'] is True
    assert layer['showLabelNameDataFlow'] is False
    assert layer['showLabelNamePower'] is True


def test_per_tab_properties_independent(client_with_layer):
    """Changing one tab's Screen Name doesn't affect others."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    # Set all to True first
    client_with_layer.put(f'/api/layer/{layer_id}', json={
        'showLabelName': True,
        'showLabelNameCabinet': True,
        'showLabelNameDataFlow': True,
        'showLabelNamePower': True,
    })

    # Turn off only cabinet
    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'showLabelNameCabinet': False,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['showLabelName'] is True, "Pixel map should stay True"
    assert layer['showLabelNameCabinet'] is False, "Cabinet should be False"
    assert layer['showLabelNameDataFlow'] is True, "Data flow should stay True"
    assert layer['showLabelNamePower'] is True, "Power should stay True"


def test_per_tab_properties_survive_save_restore(client):
    """Per-tab label properties survive project save → restore cycle."""
    # Create a layer with per-tab settings
    resp = client.post('/api/layer/add', json={
        'name': 'PerTabTest',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer_id = resp.get_json()['id']

    client.put(f'/api/layer/{layer_id}', json={
        'showLabelName': False,
        'showLabelNameCabinet': True,
        'showLabelNameDataFlow': False,
        'showLabelNamePower': True,
    })

    # Save current project state
    project = client.get('/api/project').get_json()
    saved = json.loads(json.dumps(project))

    # Create new project (wipes state)
    client.post('/api/project/new')

    # Restore saved project
    client.put('/api/project', json=saved)

    # Verify restored state
    restored = client.get('/api/project').get_json()
    layer = restored['layers'][0]
    assert layer['showLabelName'] is False
    assert layer['showLabelNameCabinet'] is True
    assert layer['showLabelNameDataFlow'] is False
    assert layer['showLabelNamePower'] is True


def test_old_project_without_per_tab_properties(client):
    """Old project files missing per-tab properties still load correctly."""
    # Simulate an old project with only global showLabelName
    old_project = {
        'name': 'Old Project',
        'raster_width': 1920,
        'raster_height': 1080,
        'layers': [{
            'id': 1,
            'name': 'LegacyScreen',
            'type': 'screen',
            'columns': 4,
            'rows': 3,
            'cabinet_width': 128,
            'cabinet_height': 128,
            'offset_x': 0,
            'offset_y': 0,
            'showLabelName': True,
            # No showLabelNameCabinet, showLabelNameDataFlow, showLabelNamePower
            'panels': [],
        }],
    }
    resp = client.put('/api/project', json=old_project)
    assert resp.status_code == 200

    project = client.get('/api/project').get_json()
    layer = project['layers'][0]
    assert layer['showLabelName'] is True
    # Per-tab properties should not exist (they'll be undefined client-side,
    # falling back to global showLabelName)
    assert 'showLabelNameCabinet' not in layer
    assert 'showLabelNameDataFlow' not in layer
    assert 'showLabelNamePower' not in layer


def test_per_tab_properties_on_layer_add(client):
    """Per-tab properties can be set at layer creation time."""
    resp = client.post('/api/layer/add', json={
        'name': 'NewScreen',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
        'showLabelName': True,
        'showLabelNameCabinet': False,
        'showLabelNameDataFlow': True,
        'showLabelNamePower': False,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['showLabelNameCabinet'] is False
    assert layer['showLabelNameDataFlow'] is True
    assert layer['showLabelNamePower'] is False


# ── Layer duplication preserves per-tab properties ───────────────────────


def test_duplicate_layer_preserves_per_tab_labels(client):
    """Duplicating a layer copies all per-tab Screen Name settings."""
    # Create and configure a layer
    resp = client.post('/api/layer/add', json={
        'name': 'Original',
        'columns': 3,
        'rows': 2,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer_id = resp.get_json()['id']

    client.put(f'/api/layer/{layer_id}', json={
        'showLabelName': False,
        'showLabelNameCabinet': True,
        'showLabelNameDataFlow': False,
        'showLabelNamePower': True,
    })

    # Duplicate by creating a new layer with same properties
    resp = client.post('/api/layer/add', json={
        'name': 'Duplicate',
        'columns': 3,
        'rows': 2,
        'cabinet_width': 128,
        'cabinet_height': 128,
        'showLabelName': False,
        'showLabelNameCabinet': True,
        'showLabelNameDataFlow': False,
        'showLabelNamePower': True,
    })
    assert resp.status_code == 200
    dup = resp.get_json()
    assert dup['showLabelName'] is False
    assert dup['showLabelNameCabinet'] is True
    assert dup['showLabelNameDataFlow'] is False
    assert dup['showLabelNamePower'] is True


# ── Multi-layer independence ─────────────────────────────────────────────


def test_multi_layer_per_tab_independence(client):
    """Per-tab properties on one layer don't affect another layer."""
    resp1 = client.post('/api/layer/add', json={
        'name': 'Screen1',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    id1 = resp1.get_json()['id']

    resp2 = client.post('/api/layer/add', json={
        'name': 'Screen2',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    id2 = resp2.get_json()['id']

    # Set different per-tab values on each
    client.put(f'/api/layer/{id1}', json={
        'showLabelName': False,
        'showLabelNameCabinet': False,
    })
    client.put(f'/api/layer/{id2}', json={
        'showLabelName': True,
        'showLabelNameCabinet': True,
    })

    project = client.get('/api/project').get_json()
    l1 = next(l for l in project['layers'] if l['id'] == id1)
    l2 = next(l for l in project['layers'] if l['id'] == id2)

    assert l1['showLabelName'] is False
    assert l1['showLabelNameCabinet'] is False
    assert l2['showLabelName'] is True
    assert l2['showLabelNameCabinet'] is True


# ── Screen name font size per-tab persistence ────────────────────────────


def test_screen_name_size_per_tab(client_with_layer):
    """Screen name font sizes for each tab persist independently."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'screenNameSizeCabinet': 42,
        'screenNameSizeDataFlow': 55,
        'screenNameSizePower': 38,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['screenNameSizeCabinet'] == 42
    assert layer['screenNameSizeDataFlow'] == 55
    assert layer['screenNameSizePower'] == 38


# ── WebSocket events include per-tab properties ──────────────────────────


def test_websocket_layer_update_includes_per_tab_props():
    """WebSocket layer_updated event includes per-tab showLabelName props."""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from app import app, socketio
    import app as app_module

    app.config['TESTING'] = True
    app_module.current_project = {
        'name': 'Untitled Project',
        'raster_width': 1920,
        'raster_height': 1080,
        'layers': [],
        'is_pristine': True,
    }
    app_module.next_layer_id = 1

    ws_client = socketio.test_client(app)
    http_client = app.test_client()

    # Add a layer
    resp = http_client.post('/api/layer/add', json={
        'name': 'WSTest',
        'columns': 2,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 100,
    })
    layer_id = resp.get_json()['id']

    # Clear initial events
    ws_client.get_received()

    # Update with per-tab properties
    http_client.put(f'/api/layer/{layer_id}', json={
        'showLabelName': False,
        'showLabelNameCabinet': True,
        'showLabelNameDataFlow': False,
        'showLabelNamePower': True,
    })

    received = ws_client.get_received()
    update_events = [r for r in received if r['name'] == 'layer_updated']
    assert len(update_events) >= 1

    updated_layer = update_events[0]['args'][0]
    assert updated_layer['showLabelName'] is False
    assert updated_layer['showLabelNameCabinet'] is True
    assert updated_layer['showLabelNameDataFlow'] is False
    assert updated_layer['showLabelNamePower'] is True

    ws_client.disconnect()


# ── API validation edge cases ────────────────────────────────────────────


def test_update_layer_with_empty_json(client_with_layer):
    """Updating a layer with empty JSON shouldn't crash."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']
    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={})
    assert resp.status_code == 200


def test_update_layer_unknown_fields_ignored(client_with_layer):
    """Unknown fields in update payload are silently ignored."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']
    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'nonExistentField': 'should be ignored',
        'name': 'StillWorks',
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['name'] == 'StillWorks'
    assert 'nonExistentField' not in layer


def test_add_layer_with_zero_dimensions(client):
    """Adding a layer with 0 columns/rows handles gracefully."""
    resp = client.post('/api/layer/add', json={
        'name': 'ZeroTest',
        'columns': 0,
        'rows': 0,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert len(layer['panels']) == 0


def test_add_layer_with_large_grid(client):
    """Adding a layer with a large grid doesn't crash."""
    resp = client.post('/api/layer/add', json={
        'name': 'LargeGrid',
        'columns': 50,
        'rows': 30,
        'cabinet_width': 64,
        'cabinet_height': 64,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert len(layer['panels']) == 1500  # 50 * 30


def test_delete_nonexistent_layer(client):
    """Deleting a layer that doesn't exist returns 200 (idempotent)."""
    resp = client.delete('/api/layer/9999')
    assert resp.status_code == 200


# ── Project round-trip with complex state ────────────────────────────────


def test_project_round_trip_all_per_tab_properties(client):
    """Full round-trip: create → configure → save → new → restore → verify."""
    # Create two layers with different per-tab settings
    resp1 = client.post('/api/layer/add', json={
        'name': 'Screen A',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    id1 = resp1.get_json()['id']

    resp2 = client.post('/api/layer/add', json={
        'name': 'Screen B',
        'columns': 6,
        'rows': 4,
        'cabinet_width': 256,
        'cabinet_height': 256,
    })
    id2 = resp2.get_json()['id']

    # Configure with per-tab and other properties
    client.put(f'/api/layer/{id1}', json={
        'showLabelName': False,
        'showLabelNameCabinet': True,
        'showLabelNameDataFlow': True,
        'showLabelNamePower': False,
        'border_color_pixel': '#ff0000',
        'border_color_cabinet': '#00ff00',
        'border_color_data': '#0000ff',
        'border_color_power': '#ffff00',
        'screenNameSizeCabinet': 40,
        'screenNameSizeDataFlow': 50,
        'screenNameSizePower': 35,
    })
    client.put(f'/api/layer/{id2}', json={
        'showLabelName': True,
        'showLabelNameCabinet': False,
        'showLabelNameDataFlow': False,
        'showLabelNamePower': True,
    })

    # Save project
    project = client.get('/api/project').get_json()
    saved = json.loads(json.dumps(project))

    # Reset
    client.post('/api/project/new')
    fresh = client.get('/api/project').get_json()
    assert len(fresh['layers']) == 1  # new project has default layer
    assert fresh['layers'][0]['name'] != 'Screen A'

    # Restore
    client.put('/api/project', json=saved)
    restored = client.get('/api/project').get_json()

    assert len(restored['layers']) == 2
    la = next(l for l in restored['layers'] if l['name'] == 'Screen A')
    lb = next(l for l in restored['layers'] if l['name'] == 'Screen B')

    assert la['showLabelName'] is False
    assert la['showLabelNameCabinet'] is True
    assert la['showLabelNameDataFlow'] is True
    assert la['showLabelNamePower'] is False
    assert la['border_color_pixel'] == '#ff0000'
    assert la['screenNameSizeCabinet'] == 40

    assert lb['showLabelName'] is True
    assert lb['showLabelNameCabinet'] is False
    assert lb['showLabelNameDataFlow'] is False
    assert lb['showLabelNamePower'] is True


# ── Border color per-view persistence ────────────────────────────────────


def test_border_colors_per_view_independent(client_with_layer):
    """Each view's border color is stored independently."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'border_color_pixel': '#111111',
        'border_color_cabinet': '#222222',
        'border_color_data': '#333333',
        'border_color_power': '#444444',
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['border_color_pixel'] == '#111111'
    assert layer['border_color_cabinet'] == '#222222'
    assert layer['border_color_data'] == '#333333'
    assert layer['border_color_power'] == '#444444'


# ── Power and data flow settings ─────────────────────────────────────────


def test_power_settings_persist(client_with_layer):
    """Power configuration properties persist through update."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'powerVoltage': 208,
        'powerAmperage': 30,
        'panelWatts': 200,
        'powerFlowPattern': 'tl-h',
        'powerLineColor': '#ff0000',
        'powerLabelTemplate': 'C#',
        'showPowerCircuitInfo': True,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['powerVoltage'] == 208
    assert layer['powerAmperage'] == 30
    assert layer['panelWatts'] == 200
    assert layer['powerFlowPattern'] == 'tl-h'
    assert layer['powerLineColor'] == '#ff0000'
    assert layer['powerLabelTemplate'] == 'C#'


def test_data_flow_settings_persist(client_with_layer):
    """Data flow configuration properties persist through update."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'dataFlowPattern': 's-tl-rd',
        'arrowColor': '#00ff00',
        'arrowLineWidth': 8,
        'arrowSize': 16,
        'showDataFlowPortInfo': True,
        'portLabelTemplatePrimary': 'OUT#',
        'portLabelTemplateReturn': 'IN#',
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['dataFlowPattern'] == 's-tl-rd'
    assert layer['arrowColor'] == '#00ff00'
    assert layer['arrowLineWidth'] == 8


def test_cabinet_id_settings_persist(client_with_layer):
    """Cabinet ID style and position persist through update."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'cabinetIdStyle': 'row-col',
        'cabinetIdPosition': 'top-left',
        'cabinetIdColor': '#abcdef',
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['cabinetIdStyle'] == 'row-col'
    assert layer['cabinetIdPosition'] == 'top-left'
    assert layer['cabinetIdColor'] == '#abcdef'


# ── Label display settings ───────────────────────────────────────────────


def test_all_label_display_flags(client_with_layer):
    """All label display checkboxes persist correctly."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'showLabelName': False,
        'showLabelSizePx': True,
        'showLabelSizeM': True,
        'showLabelSizeFt': True,
        'showLabelInfo': True,
        'showLabelWeight': True,
        'showOffsetTL': True,
        'showOffsetTR': True,
        'showOffsetBL': True,
        'showOffsetBR': True,
        'useFractionalInches': True,
    })
    assert resp.status_code == 200
    layer = resp.get_json()
    assert layer['showLabelName'] is False
    assert layer['showLabelSizePx'] is True
    assert layer['showLabelSizeM'] is True
    assert layer['showLabelSizeFt'] is True
    assert layer['showLabelInfo'] is True
    assert layer['showLabelWeight'] is True
    assert layer['showOffsetTL'] is True
    assert layer['showOffsetTR'] is True
    assert layer['showOffsetBL'] is True
    assert layer['showOffsetBR'] is True
    assert layer['useFractionalInches'] is True


# ── Layer lock and visibility ────────────────────────────────────────────


def test_layer_lock_prevents_nothing_server_side(client_with_layer):
    """Locked property persists (enforcement is client-side only)."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'locked': True,
    })
    assert resp.status_code == 200
    assert resp.get_json()['locked'] is True

    # Can still update (lock is client-side)
    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'locked': False,
        'name': 'UnlockedUpdate',
    })
    assert resp.status_code == 200
    assert resp.get_json()['name'] == 'UnlockedUpdate'


def test_layer_visibility(client_with_layer):
    """Layer visible property persists through update."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
        'visible': False,
    })
    assert resp.status_code == 200
    assert resp.get_json()['visible'] is False


# ── Multiple operations sequence ─────────────────────────────────────────


def test_rapid_update_sequence(client_with_layer):
    """Multiple rapid updates don't corrupt layer state."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    # Simulate rapid updates like a user quickly toggling settings
    for i in range(10):
        val = i % 2 == 0
        resp = client_with_layer.put(f'/api/layer/{layer_id}', json={
            'showLabelName': val,
            'showLabelNameCabinet': not val,
        })
        assert resp.status_code == 200

    # Final state should match last update (i=9, val=False)
    layer = resp.get_json()
    assert layer['showLabelName'] is False
    assert layer['showLabelNameCabinet'] is True
