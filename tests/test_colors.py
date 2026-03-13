"""Tests for color property persistence across all layer operations.

Verifies that every color property set on a layer is stored and returned
with the exact value provided — no silent defaults, no color mangling.
"""

import json
import copy


# Unique hex colors that are easy to distinguish from defaults
TEST_COLORS = {
    'color1': {'r': 17, 'g': 34, 'b': 51},           # RGB object
    'color2': {'r': 68, 'g': 85, 'b': 102},           # RGB object
    'border_color': '#1a2b3c',
    'border_color_pixel': '#2b3c4d',
    'border_color_cabinet': '#3c4d5e',
    'border_color_data': '#4d5e6f',
    'border_color_power': '#5e6f7a',
    'cabinetIdColor': '#6f7a8b',
    'arrowColor': '#7a8b9c',
    'primaryColor': '#8b9cad',
    'primaryTextColor': '#9cadbe',
    'backupColor': '#adbecf',
    'backupTextColor': '#becfda',
    'powerLineColor': '#cfda1b',
    'powerArrowColor': '#da1b2c',
    'powerLabelBgColor': '#1b2c3d',
    'powerLabelTextColor': '#2c3d4e',
    'labelsColor': '#3d4e5f',
}

# Power circuit colors (A-F)
TEST_CIRCUIT_COLORS = {
    'A': '#a11111',
    'B': '#b22222',
    'C': '#c33333',
    'D': '#d44444',
    'E': '#e55555',
    'F': '#f66666',
}


def _create_layer(client, **extra):
    """Helper to create a layer with default grid settings."""
    data = {
        'name': 'ColorTest',
        'columns': 3,
        'rows': 2,
        'cabinet_width': 128,
        'cabinet_height': 128,
    }
    data.update(extra)
    resp = client.post('/api/layer/add', json=data)
    assert resp.status_code == 200
    return resp.get_json()


# ── Create-time color tests ─────────────────────────────────────────────


def test_create_layer_with_all_hex_colors(client):
    """Setting every hex color at create time returns the exact values."""
    layer = _create_layer(client, **TEST_COLORS)

    for key, expected in TEST_COLORS.items():
        actual = layer.get(key)
        assert actual == expected, (
            f"{key}: expected {expected!r}, got {actual!r}"
        )


def test_create_layer_with_power_circuit_colors(client):
    """Power circuit color map (A-F) is stored exactly as provided."""
    layer = _create_layer(client, powerCircuitColors=TEST_CIRCUIT_COLORS)

    stored = layer.get('powerCircuitColors', {})
    for slot, expected in TEST_CIRCUIT_COLORS.items():
        actual = stored.get(slot)
        assert actual == expected, (
            f"powerCircuitColors[{slot}]: expected {expected!r}, got {actual!r}"
        )


# ── Update-time color tests ─────────────────────────────────────────────


def test_update_layer_hex_colors(client):
    """Updating every hex color via PUT returns exact values."""
    layer = _create_layer(client)
    layer_id = layer['id']

    resp = client.put(f'/api/layer/{layer_id}', json=TEST_COLORS)
    assert resp.status_code == 200
    updated = resp.get_json()

    for key, expected in TEST_COLORS.items():
        actual = updated.get(key)
        assert actual == expected, (
            f"{key}: expected {expected!r}, got {actual!r}"
        )


def test_update_layer_power_circuit_colors(client):
    """Updating power circuit colors via PUT preserves exact values."""
    layer = _create_layer(client)
    layer_id = layer['id']

    resp = client.put(f'/api/layer/{layer_id}', json={
        'powerCircuitColors': TEST_CIRCUIT_COLORS,
    })
    assert resp.status_code == 200
    updated = resp.get_json()

    stored = updated.get('powerCircuitColors', {})
    for slot, expected in TEST_CIRCUIT_COLORS.items():
        actual = stored.get(slot)
        assert actual == expected, (
            f"powerCircuitColors[{slot}]: expected {expected!r}, got {actual!r}"
        )


# ── Individual color field tests ─────────────────────────────────────────


def test_color1_rgb_object(client):
    """color1 stored as RGB object {r, g, b}."""
    layer = _create_layer(client, color1={'r': 255, 'g': 0, 'b': 128})
    assert layer['color1'] == {'r': 255, 'g': 0, 'b': 128}


def test_color2_rgb_object(client):
    """color2 stored as RGB object {r, g, b}."""
    layer = _create_layer(client, color2={'r': 0, 'g': 255, 'b': 64})
    assert layer['color2'] == {'r': 0, 'g': 255, 'b': 64}


def test_border_color_variants(client):
    """Each per-view border color is independent and stored exactly."""
    colors = {
        'border_color': '#ff0000',
        'border_color_pixel': '#00ff00',
        'border_color_cabinet': '#0000ff',
        'border_color_data': '#ffff00',
        'border_color_power': '#ff00ff',
    }
    layer = _create_layer(client, **colors)
    for key, expected in colors.items():
        assert layer[key] == expected, f"{key}: {layer.get(key)} != {expected}"


def test_data_flow_colors(client):
    """Data flow colors (arrow, primary, backup) stored exactly."""
    colors = {
        'arrowColor': '#123456',
        'primaryColor': '#234567',
        'primaryTextColor': '#345678',
        'backupColor': '#456789',
        'backupTextColor': '#56789a',
    }
    layer = _create_layer(client, **colors)
    for key, expected in colors.items():
        assert layer[key] == expected, f"{key}: {layer.get(key)} != {expected}"


def test_power_flow_colors(client):
    """Power flow colors stored exactly."""
    colors = {
        'powerLineColor': '#abcdef',
        'powerArrowColor': '#fedcba',
        'powerLabelBgColor': '#112233',
        'powerLabelTextColor': '#445566',
    }
    layer = _create_layer(client, **colors)
    for key, expected in colors.items():
        assert layer[key] == expected, f"{key}: {layer.get(key)} != {expected}"


def test_cabinet_id_color(client):
    """Cabinet ID color stored exactly."""
    layer = _create_layer(client, cabinetIdColor='#aabbcc')
    assert layer['cabinetIdColor'] == '#aabbcc'


def test_labels_color(client):
    """Labels color stored exactly."""
    layer = _create_layer(client, labelsColor='#ddeeff')
    assert layer['labelsColor'] == '#ddeeff'


# ── Color persistence through duplicate ──────────────────────────────────


def test_duplicate_preserves_all_colors(client):
    """Duplicating a layer via add_layer preserves every color property."""
    # Combine all colors into one layer
    all_colors = dict(TEST_COLORS)
    all_colors['powerCircuitColors'] = TEST_CIRCUIT_COLORS

    # Simulate duplicate: create with all colors (like duplicateLayer does)
    layer = _create_layer(client, **all_colors)

    for key, expected in TEST_COLORS.items():
        actual = layer.get(key)
        assert actual == expected, (
            f"Duplicate {key}: expected {expected!r}, got {actual!r}"
        )
    stored_circuits = layer.get('powerCircuitColors', {})
    for slot, expected in TEST_CIRCUIT_COLORS.items():
        actual = stored_circuits.get(slot)
        assert actual == expected, (
            f"Duplicate powerCircuitColors[{slot}]: expected {expected!r}, got {actual!r}"
        )


# ── Color update doesn't affect other colors ────────────────────────────


def test_update_one_color_doesnt_change_others(client):
    """Updating a single color leaves all other colors untouched."""
    layer = _create_layer(client, **TEST_COLORS)
    layer_id = layer['id']

    # Update only arrowColor
    resp = client.put(f'/api/layer/{layer_id}', json={
        'arrowColor': '#000000',
    })
    assert resp.status_code == 200
    updated = resp.get_json()

    # arrowColor changed
    assert updated['arrowColor'] == '#000000'

    # All other colors unchanged
    for key, expected in TEST_COLORS.items():
        if key == 'arrowColor':
            continue
        actual = updated.get(key)
        assert actual == expected, (
            f"{key} changed unexpectedly: expected {expected!r}, got {actual!r}"
        )


# ── Edge cases ───────────────────────────────────────────────────────────


def test_color_hex_case_preserved(client):
    """Hex color case is preserved exactly as sent (no uppercasing)."""
    layer = _create_layer(client, arrowColor='#aAbBcC')
    assert layer['arrowColor'] == '#aAbBcC'


def test_color_survives_project_save_restore(client):
    """Colors survive a full save/restore cycle."""
    layer = _create_layer(client, **TEST_COLORS)

    # Get current project state
    resp = client.get('/api/project')
    assert resp.status_code == 200
    project = resp.get_json()

    # Restore (simulates undo/redo or file load)
    resp = client.put('/api/project', json=project)
    assert resp.status_code == 200

    # Get project data after restore
    resp = client.get('/api/project')
    assert resp.status_code == 200
    project = resp.get_json()
    restored_layer = project['layers'][0]

    for key, expected in TEST_COLORS.items():
        actual = restored_layer.get(key)
        assert actual == expected, (
            f"After restore, {key}: expected {expected!r}, got {actual!r}"
        )


def test_power_circuit_colors_partial_update(client):
    """Updating one circuit color slot doesn't wipe other slots."""
    layer = _create_layer(client, powerCircuitColors=TEST_CIRCUIT_COLORS)
    layer_id = layer['id']

    # Update with only slot A changed
    new_colors = copy.deepcopy(TEST_CIRCUIT_COLORS)
    new_colors['A'] = '#ffffff'

    resp = client.put(f'/api/layer/{layer_id}', json={
        'powerCircuitColors': new_colors,
    })
    assert resp.status_code == 200
    updated = resp.get_json()

    stored = updated.get('powerCircuitColors', {})
    assert stored['A'] == '#ffffff'
    # Other slots unchanged
    for slot in ['B', 'C', 'D', 'E', 'F']:
        assert stored[slot] == TEST_CIRCUIT_COLORS[slot], (
            f"Slot {slot} changed unexpectedly"
        )
