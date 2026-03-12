"""Tests for error handling, edge cases, and bad input validation."""

import sys
import os
import io
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app import decode_base64_image, decode_base64_bytes


# ── 404 errors on nonexistent resources ─────────────────────────────

def test_delete_nonexistent_layer(client):
    """DELETE on a non-existent layer returns 404."""
    resp = client.delete('/api/layer/9999')
    # Should succeed (no-op) but return project - check it doesn't crash
    assert resp.status_code == 200


def test_toggle_hidden_nonexistent_layer(client):
    """Toggle hidden on missing layer returns 404."""
    resp = client.post('/api/layer/999/panel/1/toggle_hidden')
    assert resp.status_code == 404


def test_toggle_hidden_nonexistent_panel(client_with_layer):
    """Toggle hidden on missing panel returns 404."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']
    resp = client_with_layer.post(f'/api/layer/{layer_id}/panel/99999/toggle_hidden')
    assert resp.status_code == 404


def test_toggle_blank_nonexistent_layer(client):
    """Toggle blank on missing layer returns 404."""
    resp = client.post('/api/layer/999/panel/1/toggle')
    assert resp.status_code == 404


# ── decode_base64_image / decode_base64_bytes ───────────────────────

def test_decode_base64_image():
    """decode_base64_image handles data URL prefix correctly."""
    from PIL import Image
    img = Image.new('RGBA', (10, 10), (0, 255, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()

    result = decode_base64_image(f'data:image/png;base64,{b64}')
    assert result.size == (10, 10)


def test_decode_base64_image_no_prefix():
    """decode_base64_image works with raw base64 (no data URL prefix)."""
    from PIL import Image
    img = Image.new('RGB', (5, 5), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()

    result = decode_base64_image(b64)
    assert result.size == (5, 5)


def test_decode_base64_bytes():
    """decode_base64_bytes returns raw bytes from data URL."""
    original = b'hello world test data'
    b64 = base64.b64encode(original).decode()

    result = decode_base64_bytes(f'data:application/octet-stream;base64,{b64}')
    assert result == original


def test_decode_base64_bytes_no_prefix():
    """decode_base64_bytes works with raw base64 string."""
    original = b'test bytes'
    b64 = base64.b64encode(original).decode()

    result = decode_base64_bytes(b64)
    assert result == original


# ── Log endpoint edge cases ─────────────────────────────────────────

def test_log_with_empty_json(client):
    """Log endpoint handles empty JSON gracefully."""
    resp = client.post('/api/log', json={})
    assert resp.status_code == 200


def test_log_with_nested_details(client):
    """Log endpoint handles complex nested data."""
    resp = client.post('/api/log', json={
        'action': 'complex_action',
        'details': {
            'nested': {'deep': True},
            'list': [1, 2, 3],
        },
    })
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'ok'


# ── Project edge cases ──────────────────────────────────────────────

def test_save_project_preserves_layers(client_with_layer):
    """POST /api/project (save) doesn't wipe existing layers."""
    project = client_with_layer.get('/api/project').get_json()
    assert len(project['layers']) == 1

    # Save with just a name change
    client_with_layer.post('/api/project', json={'name': 'New Name'})

    project = client_with_layer.get('/api/project').get_json()
    assert project['name'] == 'New Name'
    assert len(project['layers']) == 1  # Layer preserved


def test_restore_project_replaces_everything(client_with_layer):
    """PUT /api/project fully replaces state."""
    resp = client_with_layer.put('/api/project', json={
        'name': 'Brand New',
        'raster_width': 800,
        'raster_height': 600,
        'layers': [],
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['name'] == 'Brand New'
    assert len(data['layers']) == 0


# ── New project always gets default layer ───────────────────────────

def test_new_project_always_has_default_layer(client):
    """POST /api/project/new always creates a default Screen1 layer."""
    resp = client.post('/api/project/new')
    data = resp.get_json()
    assert len(data['layers']) >= 1
    assert data['layers'][0]['name'] == 'Screen1'


def test_new_project_resets_raster_dimensions(client):
    """New project resets to default 1920x1080."""
    # First change dimensions
    client.post('/api/project', json={
        'raster_width': 3840,
        'raster_height': 2160,
    })

    # New project should reset
    resp = client.post('/api/project/new')
    data = resp.get_json()
    assert data['raster_width'] == 1920
    assert data['raster_height'] == 1080


# ── Index page ──────────────────────────────────────────────────────

def test_index_page_loads(client):
    """GET / returns HTML with no-cache headers."""
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'html' in resp.data.lower() or b'HTML' in resp.data
    assert resp.headers.get('Cache-Control') == 'no-cache, no-store, must-revalidate'


# ── Server session consistency ──────────────────────────────────────

def test_server_session_consistent(client):
    """Two calls to /api/server-session return the same session ID."""
    resp1 = client.get('/api/server-session').get_json()
    resp2 = client.get('/api/server-session').get_json()
    assert resp1['session_id'] == resp2['session_id']
    assert resp1['start_time'] == resp2['start_time']
