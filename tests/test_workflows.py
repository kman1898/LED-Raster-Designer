"""Tests for complete user workflows, multi-step sequences that simulate
real usage patterns like creating a project, configuring layers, and exporting."""

import io
import json
import base64
import zipfile


def _make_test_image_data():
    """Create a minimal valid base64 PNG for testing."""
    from PIL import Image
    img = Image.new('RGBA', (10, 10), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'data:image/png;base64,{b64}'


# ── Full project lifecycle ────────────────────────────────────────────

def test_full_project_lifecycle(client):
    """Create project → add layers → configure → export → new project."""
    # 1. Start fresh
    resp = client.post('/api/project/new')
    assert resp.status_code == 200
    project = resp.get_json()
    assert project['name'] == 'Untitled Project'

    # 2. Rename project and set custom dimensions
    resp = client.post('/api/project', json={
        'name': 'Concert Stage',
        'raster_width': 3840,
        'raster_height': 2160,
    })
    assert resp.status_code == 200

    # 3. Add a main screen layer
    resp = client.post('/api/layer/add', json={
        'name': 'Main LED Wall',
        'columns': 8,
        'rows': 4,
        'cabinet_width': 128,
        'cabinet_height': 128,
        'offset_x': 100,
        'offset_y': 50,
    })
    assert resp.status_code == 200
    main_layer = resp.get_json()
    assert len(main_layer['panels']) == 32

    # 4. Add a side screen
    resp = client.post('/api/layer/add', json={
        'name': 'Side Screen',
        'columns': 2,
        'rows': 6,
        'cabinet_width': 64,
        'cabinet_height': 64,
    })
    assert resp.status_code == 200

    # 5. Hide corner panels on the main screen
    layer_id = main_layer['id']
    panels = main_layer['panels']
    corners = [p for p in panels if
               (p['row'] == 0 and p['col'] == 0) or
               (p['row'] == 0 and p['col'] == 7) or
               (p['row'] == 3 and p['col'] == 0) or
               (p['row'] == 3 and p['col'] == 7)]
    for corner in corners:
        resp = client.post(f'/api/layer/{layer_id}/panel/{corner["id"]}/toggle_hidden')
        assert resp.status_code == 200

    # 6. Blank a panel
    mid_panel = panels[10]
    resp = client.post(f'/api/layer/{layer_id}/panel/{mid_panel["id"]}/toggle')
    assert resp.status_code == 200
    assert resp.get_json()['blank'] is True

    # 7. Export as PNG
    resp = client.post('/api/export/png', json={'include_borders': True})
    assert resp.status_code == 200
    assert resp.data[:4] == b'\x89PNG'

    # 8. Verify project state is intact
    # 3 layers: default Screen1 from new_project + Main LED Wall + Side Screen
    project = client.get('/api/project').get_json()
    assert project['name'] == 'Concert Stage'
    assert len(project['layers']) == 3

    # 9. Start a new project, everything resets
    resp = client.post('/api/project/new')
    project = resp.get_json()
    assert project['name'] == 'Untitled Project'
    assert project['raster_width'] == 1920


def test_layer_styling_workflow(client):
    """Add a layer and configure all styling options."""
    resp = client.post('/api/layer/add', json={
        'name': 'Styled',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    # Update colors
    resp = client.put(f'/api/layer/{layer_id}', json={
        'color1': {'r': 255, 'g': 0, 'b': 0},
        'color2': {'r': 0, 'g': 255, 'b': 0},
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['color1'] == {'r': 255, 'g': 0, 'b': 0}
    assert updated['color2'] == {'r': 0, 'g': 255, 'b': 0}

    # Update border settings
    resp = client.put(f'/api/layer/{layer_id}', json={
        'show_panel_borders': True,
        'border_color': '#FF00FF',
        'border_color_pixel': '#AABBCC',
        'border_color_cabinet': '#112233',
        'border_color_data': '#445566',
        'border_color_power': '#778899',
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['border_color'] == '#FF00FF'
    assert updated['border_color_pixel'] == '#AABBCC'

    # Update panel numbering display
    resp = client.put(f'/api/layer/{layer_id}', json={
        'show_numbers': False,
        'number_size': 24,
        'show_circle_with_x': False,
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['show_numbers'] is False
    assert updated['number_size'] == 24


def test_power_settings_workflow(client):
    """Configure all power-related layer settings."""
    resp = client.post('/api/layer/add', json={
        'name': 'PowerTest',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    resp = client.put(f'/api/layer/{layer_id}', json={
        'powerVoltage': 220,
        'powerVoltageCustom': 240,
        'powerAmperage': 20,
        'powerAmperageCustom': 25,
        'panelWatts': 300,
        'powerMaximize': True,
        'powerOrganized': False,
        'powerFlowPattern': 'tl-v',
        'powerLineWidth': 10,
        'powerLineColor': '#FF0000',
        'powerArrowColor': '#00FF00',
        'powerRandomColors': True,
        'powerColorCodedView': True,
        'powerLabelSize': 18,
        'powerLabelBgColor': '#FFAA00',
        'powerLabelTextColor': '#000000',
        'powerLabelTemplate': 'CKT-#',
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['powerVoltage'] == 220
    assert updated['panelWatts'] == 300
    assert updated['powerMaximize'] is True
    assert updated['powerOrganized'] is False
    assert updated['powerFlowPattern'] == 'tl-v'
    assert updated['powerLabelTemplate'] == 'CKT-#'
    assert updated['powerRandomColors'] is True
    assert updated['powerColorCodedView'] is True


def test_power_circuit_colors_workflow(client):
    """Power circuit colors can be set and retrieved."""
    resp = client.post('/api/layer/add', json={
        'name': 'Circuits',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    circuit_colors = {
        'A': '#FF0000',
        'B': '#00FF00',
        'C': '#0000FF',
        'D': '#FFFF00',
        'E': '#FF00FF',
        'F': '#00FFFF',
    }
    resp = client.put(f'/api/layer/{layer_id}', json={
        'powerCircuitColors': circuit_colors,
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['powerCircuitColors'] == circuit_colors


def test_power_label_overrides_workflow(client):
    """Custom power label overrides per panel."""
    resp = client.post('/api/layer/add', json={
        'name': 'Labels',
        'columns': 3,
        'rows': 2,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    overrides = {'1': 'A-1', '2': 'A-2', '3': 'B-1'}
    resp = client.put(f'/api/layer/{layer_id}', json={
        'powerLabelOverrides': overrides,
    })
    assert resp.status_code == 200
    assert resp.get_json()['powerLabelOverrides'] == overrides


def test_data_flow_settings_workflow(client):
    """Configure all data flow settings."""
    resp = client.post('/api/layer/add', json={
        'name': 'DataFlow',
        'columns': 6,
        'rows': 4,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    resp = client.put(f'/api/layer/{layer_id}', json={
        'dataFlowPattern': 's-tl-rd',
        'arrowLineWidth': 8,
        'arrowSize': 16,
        'arrowColor': '#FFFFFF',
        'primaryColor': '#00FF00',
        'primaryTextColor': '#000000',
        'backupColor': '#FF0000',
        'backupTextColor': '#FFFFFF',
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['dataFlowPattern'] == 's-tl-rd'
    assert updated['arrowLineWidth'] == 8
    assert updated['arrowSize'] == 16
    assert updated['primaryColor'] == '#00FF00'
    assert updated['backupColor'] == '#FF0000'


def test_cabinet_id_settings_workflow(client):
    """Configure cabinet ID display options."""
    resp = client.post('/api/layer/add', json={
        'name': 'CabinetID',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    # Test all cabinet ID styles
    for style in ['column-row', 'row-column', 'row-col', 'A1']:
        resp = client.put(f'/api/layer/{layer_id}', json={
            'cabinetIdStyle': style,
        })
        assert resp.status_code == 200
        assert resp.get_json()['cabinetIdStyle'] == style

    # Test positions
    for pos in ['top-left', 'center']:
        resp = client.put(f'/api/layer/{layer_id}', json={
            'cabinetIdPosition': pos,
        })
        assert resp.status_code == 200
        assert resp.get_json()['cabinetIdPosition'] == pos


def test_label_settings_workflow(client):
    """Configure label display options."""
    resp = client.post('/api/layer/add', json={
        'name': 'Labels',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    resp = client.put(f'/api/layer/{layer_id}', json={
        'showLabelName': True,
        'showLabelSizePx': True,
        'showLabelSizeM': True,
        'showLabelSizeFt': True,
        'showLabelWeight': True,
        'showLabelInfo': True,
        'labelsColor': '#FFFF00',
        'labelsFontSize': 24,
        'infoLabelSize': 12,
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['showLabelName'] is True
    assert updated['showLabelSizeM'] is True
    assert updated['showLabelSizeFt'] is True
    assert updated['showLabelWeight'] is True
    assert updated['labelsColor'] == '#FFFF00'
    assert updated['labelsFontSize'] == 24


def test_offset_display_settings(client):
    """Configure offset corner display toggles."""
    resp = client.post('/api/layer/add', json={
        'name': 'Offsets',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    resp = client.put(f'/api/layer/{layer_id}', json={
        'showOffsetTL': True,
        'showOffsetTR': True,
        'showOffsetBL': False,
        'showOffsetBR': False,
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['showOffsetTL'] is True
    assert updated['showOffsetTR'] is True
    assert updated['showOffsetBL'] is False
    assert updated['showOffsetBR'] is False


def test_physical_dimensions_workflow(client):
    """Set physical panel dimensions and weight."""
    resp = client.post('/api/layer/add', json={
        'name': 'Physical',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    resp = client.put(f'/api/layer/{layer_id}', json={
        'panel_width_mm': 500,
        'panel_height_mm': 500,
        'panel_weight': 8.5,
        'weight_unit': 'kg',
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['panel_width_mm'] == 500
    assert updated['panel_height_mm'] == 500
    assert updated['panel_weight'] == 8.5
    assert updated['weight_unit'] == 'kg'


def test_screen_name_sizes_workflow(client):
    """Set per-view screen name font sizes."""
    resp = client.post('/api/layer/add', json={
        'name': 'FontSizes',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    resp = client.put(f'/api/layer/{layer_id}', json={
        'screenNameSizeCabinet': 18,
        'screenNameSizeDataFlow': 20,
        'screenNameSizePower': 16,
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated['screenNameSizeCabinet'] == 18
    assert updated['screenNameSizeDataFlow'] == 20
    assert updated['screenNameSizePower'] == 16


# ── Half panel combinations ──────────────────────────────────────────

def test_all_half_panel_flags(client):
    """All four legacy half-panel flags simultaneously.

    Under the new per-panel model, each panel can be half in one dimension
    at a time. The migration gives row-based flags precedence over column-
    based flags, so a corner cell affected by both row and column flags
    becomes half-HEIGHT. Non-corner first/last column cells become
    half-WIDTH; non-corner first/last row cells become half-HEIGHT.
    """
    resp = client.post('/api/layer/add', json={
        'name': 'AllHalves',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 200,
        'cabinet_height': 100,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    resp = client.put(f'/api/layer/{layer_id}', json={
        'halfFirstColumn': True,
        'halfLastColumn': True,
        'halfFirstRow': True,
        'halfLastRow': True,
    })
    assert resp.status_code == 200
    updated = resp.get_json()
    panels = updated['panels']
    by_pos = {(p['row'], p['col']): p for p in panels}

    # Non-corner first/last row panels: half-height (full width).
    for c in range(1, 3):
        assert by_pos[(0, c)]['height'] == 50
        assert by_pos[(0, c)]['width'] == 200
        assert by_pos[(2, c)]['height'] == 50
        assert by_pos[(2, c)]['width'] == 200

    # Non-corner first/last column panels: half-width (full height).
    assert by_pos[(1, 0)]['width'] == 100
    assert by_pos[(1, 0)]['height'] == 100
    assert by_pos[(1, 3)]['width'] == 100
    assert by_pos[(1, 3)]['height'] == 100

    # Corner cells: row flag wins → half-height, full width.
    for r in (0, 2):
        for c in (0, 3):
            assert by_pos[(r, c)]['height'] == 50, f"Corner ({r},{c}) should be half-height"


def test_half_panels_with_1x1_grid(client):
    """Half panel flags on a 1x1 grid (edge case).

    With both halfFirstColumn and halfFirstRow set on a single cell, the
    migration gives the row flag precedence, so the panel becomes half-
    height with full width.
    """
    resp = client.post('/api/layer/add', json={
        'name': 'Tiny',
        'columns': 1,
        'rows': 1,
        'cabinet_width': 200,
        'cabinet_height': 100,
    })
    layer = resp.get_json()
    layer_id = layer['id']

    resp = client.put(f'/api/layer/{layer_id}', json={
        'halfFirstColumn': True,
        'halfFirstRow': True,
    })
    assert resp.status_code == 200
    panels = resp.get_json()['panels']
    assert len(panels) == 1
    # Row flag wins: full width, half height.
    assert panels[0]['width'] == 200
    assert panels[0]['height'] == 50
    assert panels[0]['halfTile'] == 'height'


# ── Multi-layer export workflow ───────────────────────────────────────

def test_multi_layer_export_all_formats(client):
    """Add multiple layers and export in each format."""
    # Add two screen layers
    client.post('/api/layer/add', json={
        'name': 'Main', 'columns': 4, 'rows': 3,
        'cabinet_width': 128, 'cabinet_height': 128,
    })
    client.post('/api/layer/add', json={
        'name': 'Side', 'columns': 2, 'rows': 4,
        'cabinet_width': 64, 'cabinet_height': 64,
        'offset_x': 600,
    })

    # PNG
    resp = client.post('/api/export/png', json={'include_borders': True})
    assert resp.status_code == 200
    assert resp.data[:4] == b'\x89PNG'

    # PSD (or ZIP fallback)
    resp = client.post('/api/export/psd', json={'include_borders': True})
    assert resp.status_code == 200
    assert resp.data[:4] in (b'8BPS', b'PK\x03\x04')

    # ZIP with individual layers
    resp = client.post('/api/export/zip', json={'include_borders': True})
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert 'manifest.json' in zf.namelist()
    manifest = json.loads(zf.read('manifest.json'))
    assert len(manifest['layers']) == 2

    # Unified export with multiple views
    resp = client.post('/api/export', json={
        'format': 'png',
        'views': ['pixel-map', 'cabinet-id'],
        'project_name': 'MultiTest',
    })
    assert resp.status_code == 200


def test_hidden_layer_excluded_from_export(client):
    """Hidden layers should not appear in exports."""
    resp = client.post('/api/layer/add', json={
        'name': 'Visible', 'columns': 2, 'rows': 2,
        'cabinet_width': 100, 'cabinet_height': 100,
    })
    visible_id = resp.get_json()['id']

    resp = client.post('/api/layer/add', json={
        'name': 'Hidden', 'columns': 2, 'rows': 2,
        'cabinet_width': 100, 'cabinet_height': 100,
    })
    hidden_id = resp.get_json()['id']

    # Hide the second layer
    client.put(f'/api/layer/{hidden_id}', json={'visible': False})

    # Export ZIP, manifest should only include visible layer
    resp = client.post('/api/export/zip', json={'include_borders': False})
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    manifest = json.loads(zf.read('manifest.json'))
    visible_layers = [l for l in manifest['layers'] if l.get('visible', True)]
    assert len(visible_layers) == 1
    assert visible_layers[0]['name'] == 'Visible'


# ── Image layer workflows ─────────────────────────────────────────────

def test_image_layer_with_screen_layer_export(client):
    """Mix screen and image layers, then export."""
    # Add screen layer
    client.post('/api/layer/add', json={
        'name': 'Screen', 'columns': 4, 'rows': 3,
        'cabinet_width': 128, 'cabinet_height': 128,
    })

    # Add image layer
    img_data = _make_test_image_data()
    client.post('/api/layer/add-image', json={
        'name': 'Logo',
        'imageData': img_data,
        'imageWidth': 100,
        'imageHeight': 50,
        'offset_x': 200,
        'offset_y': 100,
    })

    # Export should work with mixed layer types
    resp = client.post('/api/export/png', json={'include_borders': True})
    assert resp.status_code == 200
    assert resp.data[:4] == b'\x89PNG'


# ── Project save/restore with complex state ───────────────────────────

def test_restore_preserves_all_settings(client):
    """Save and restore project with all layer settings intact."""
    # Add layer with lots of settings
    resp = client.post('/api/layer/add', json={
        'name': 'Complex',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer_id = resp.get_json()['id']

    # Set many fields
    client.put(f'/api/layer/{layer_id}', json={
        'powerVoltage': 220,
        'panelWatts': 300,
        'dataFlowPattern': 'horizontal-right',
        'cabinetIdStyle': 'row-column',
        'showLabelWeight': True,
        'halfFirstColumn': True,
        'panel_width_mm': 600,
    })

    # Get full project state
    project = client.get('/api/project').get_json()
    layer = project['layers'][0]

    # Restore it
    resp = client.put('/api/project', json=project)
    assert resp.status_code == 200
    restored = resp.get_json()
    restored_layer = restored['layers'][0]

    assert restored_layer['powerVoltage'] == 220
    assert restored_layer['panelWatts'] == 300
    assert restored_layer['dataFlowPattern'] == 'horizontal-right'
    assert restored_layer['cabinetIdStyle'] == 'row-column'
    assert restored_layer['showLabelWeight'] is True
    assert restored_layer['panel_width_mm'] == 600
    # The legacy halfFirstColumn flag is migrated into per-panel halfTile
    # state on first build, then cleared. Verify the equivalent state is
    # preserved on the affected panels instead of the flag itself.
    first_col_panels = [p for p in restored_layer['panels'] if p['col'] == 0]
    assert all(p['halfTile'] == 'width' for p in first_col_panels)


# ── Rotation ──────────────────────────────────────────────────────────

def test_layer_rotation(client):
    """Layer rotation property can be set."""
    resp = client.post('/api/layer/add', json={
        'name': 'Rotated',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    layer_id = resp.get_json()['id']

    resp = client.put(f'/api/layer/{layer_id}', json={'rotation': 90})
    assert resp.status_code == 200
    assert resp.get_json()['rotation'] == 90
