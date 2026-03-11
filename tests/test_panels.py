"""Tests for panel toggle operations."""


def test_toggle_panel_blank(client_with_layer):
    """POST toggle blank flips the blank state of a panel."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']
    panel_id = project['layers'][0]['panels'][0]['id']

    # Toggle blank on
    resp = client_with_layer.post(f'/api/layer/{layer_id}/panel/{panel_id}/toggle')
    assert resp.status_code == 200
    assert resp.get_json()['blank'] is True

    # Toggle blank off
    resp = client_with_layer.post(f'/api/layer/{layer_id}/panel/{panel_id}/toggle')
    assert resp.status_code == 200
    assert resp.get_json()['blank'] is False


def test_toggle_panel_hidden(client_with_layer):
    """POST toggle hidden flips the hidden state of a panel."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']
    panel_id = project['layers'][0]['panels'][0]['id']

    resp = client_with_layer.post(f'/api/layer/{layer_id}/panel/{panel_id}/toggle_hidden')
    assert resp.status_code == 200
    assert resp.get_json()['hidden'] is True

    resp = client_with_layer.post(f'/api/layer/{layer_id}/panel/{panel_id}/toggle_hidden')
    assert resp.status_code == 200
    assert resp.get_json()['hidden'] is False


def test_toggle_nonexistent_layer(client):
    """Toggling a panel on a missing layer returns 404."""
    resp = client.post('/api/layer/999/panel/1/toggle')
    assert resp.status_code == 404


def test_toggle_nonexistent_panel(client_with_layer):
    """Toggling a missing panel returns 404."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']

    resp = client_with_layer.post(f'/api/layer/{layer_id}/panel/9999/toggle')
    assert resp.status_code == 404


def test_panel_checkerboard_pattern(client):
    """Panels alternate is_color1 in a checkerboard pattern."""
    resp = client.post('/api/layer/add', json={
        'name': 'Checker',
        'columns': 3,
        'rows': 3,
        'cabinet_width': 100,
        'cabinet_height': 100,
    })
    panels = resp.get_json()['panels']
    for p in panels:
        expected = (p['row'] + p['col']) % 2 == 0
        assert p['is_color1'] == expected, f"Panel row={p['row']} col={p['col']}"
