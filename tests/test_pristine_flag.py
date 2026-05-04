"""Tests for the is_pristine flag that prevents startup preferences from
overwriting loaded projects on reconnect or page refresh."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import app as app_module
from app import app, socketio


def _fresh_project():
    """Reset to a pristine default project."""
    app_module.current_project = {
        'name': 'Untitled Project',
        'raster_width': 1920,
        'raster_height': 1080,
        'layers': [],
        'is_pristine': True
    }
    app_module.next_layer_id = 1


# ── Initial state ──────────────────────────────────────────────────────


def test_default_project_is_pristine():
    """A fresh default project should have is_pristine=True."""
    app.config['TESTING'] = True
    _fresh_project()
    with app.test_client() as client:
        resp = client.get('/api/project')
        data = resp.get_json()
        assert data['is_pristine'] is True


def test_new_project_is_pristine():
    """POST /api/project/new should produce a pristine project."""
    app.config['TESTING'] = True
    _fresh_project()
    with app.test_client() as client:
        resp = client.post('/api/project/new')
        data = resp.get_json()
        assert data['is_pristine'] is True
        assert data['name'] == 'Untitled Project'
        assert len(data['layers']) == 1


# ── Mutations clear is_pristine ────────────────────────────────────────


def test_save_project_clears_pristine():
    """POST /api/project (save) should set is_pristine=False."""
    app.config['TESTING'] = True
    _fresh_project()
    with app.test_client() as client:
        client.post('/api/project', json={'name': 'My Wall'})
        resp = client.get('/api/project')
        data = resp.get_json()
        assert data['is_pristine'] is False


def test_restore_project_clears_pristine():
    """PUT /api/project (restore/file-load) should set is_pristine=False."""
    app.config['TESTING'] = True
    _fresh_project()
    with app.test_client() as client:
        client.put('/api/project', json={
            'name': 'Untitled Project',
            'raster_width': 3840,
            'raster_height': 2160,
            'layers': []
        })
        resp = client.get('/api/project')
        data = resp.get_json()
        assert data['is_pristine'] is False


def test_add_layer_clears_pristine():
    """Adding a layer should set is_pristine=False."""
    app.config['TESTING'] = True
    _fresh_project()
    with app.test_client() as client:
        client.post('/api/layer/add', json={
            'name': 'Screen1',
            'columns': 8,
            'rows': 5,
            'cabinet_width': 128,
            'cabinet_height': 128,
        })
        resp = client.get('/api/project')
        data = resp.get_json()
        assert data['is_pristine'] is False


def test_add_image_layer_clears_pristine():
    """Adding an image layer should set is_pristine=False."""
    app.config['TESTING'] = True
    _fresh_project()
    with app.test_client() as client:
        client.post('/api/layer/add-image', json={
            'name': 'Image1',
            'imageData': '',
            'imageWidth': 100,
            'imageHeight': 100,
        })
        resp = client.get('/api/project')
        data = resp.get_json()
        assert data['is_pristine'] is False


def test_update_layer_clears_pristine():
    """Updating a layer should set is_pristine=False."""
    app.config['TESTING'] = True
    _fresh_project()
    with app.test_client() as client:
        resp = client.post('/api/layer/add', json={
            'name': 'Screen1',
            'columns': 4,
            'rows': 3,
            'cabinet_width': 128,
            'cabinet_height': 128,
        })
        layer_id = resp.get_json()['id']

        # Reset pristine to test that update_layer itself clears it
        app_module.current_project['is_pristine'] = True

        client.put(f'/api/layer/{layer_id}', json={'name': 'Renamed'})
        resp = client.get('/api/project')
        data = resp.get_json()
        assert data['is_pristine'] is False


def test_delete_layer_clears_pristine():
    """Deleting a layer should set is_pristine=False."""
    app.config['TESTING'] = True
    _fresh_project()
    with app.test_client() as client:
        resp = client.post('/api/layer/add', json={
            'name': 'Screen1',
            'columns': 4,
            'rows': 3,
            'cabinet_width': 128,
            'cabinet_height': 128,
        })
        layer_id = resp.get_json()['id']

        # Reset pristine to test that delete_layer itself clears it
        app_module.current_project['is_pristine'] = True

        client.delete(f'/api/layer/{layer_id}')
        resp = client.get('/api/project')
        data = resp.get_json()
        assert data['is_pristine'] is False


# ── Pristine flag survives new project cycle ───────────────────────────


def test_new_project_after_load_restores_pristine():
    """After loading a file (not pristine), creating a new project
    should reset is_pristine back to True."""
    app.config['TESTING'] = True
    _fresh_project()
    with app.test_client() as client:
        # Simulate file load
        client.put('/api/project', json={
            'name': 'Loaded File',
            'raster_width': 3840,
            'raster_height': 2160,
            'layers': []
        })
        resp = client.get('/api/project')
        assert resp.get_json()['is_pristine'] is False

        # New project should be pristine again
        resp = client.post('/api/project/new')
        data = resp.get_json()
        assert data['is_pristine'] is True


# ── WebSocket reconnect scenarios ──────────────────────────────────────


def test_socket_connect_sends_pristine_flag():
    """On socket connect, project_data should include is_pristine."""
    app.config['TESTING'] = True
    _fresh_project()
    app_module.initialize_default_layer()
    ws = socketio.test_client(app)
    received = ws.get_received()
    project_events = [r for r in received if r['name'] == 'project_data']
    assert len(project_events) >= 1
    data = project_events[0]['args'][0]
    assert 'is_pristine' in data
    assert data['is_pristine'] is True
    ws.disconnect()


def test_socket_reconnect_after_file_load_not_pristine():
    """After a file load, reconnecting should show is_pristine=False."""
    app.config['TESTING'] = True
    _fresh_project()
    with app.test_client() as http_client:
        # Simulate file load
        http_client.put('/api/project', json={
            'name': 'Untitled Project',
            'raster_width': 3840,
            'raster_height': 2160,
            'layers': [{'id': 1, 'name': 'Screen1', 'columns': 90, 'rows': 3,
                        'cabinet_width': 128, 'cabinet_height': 128,
                        'offset_x': 0, 'offset_y': 0, 'panels': []}]
        })

    # Simulate reconnect, new socket connection
    ws = socketio.test_client(app)
    received = ws.get_received()
    project_events = [r for r in received if r['name'] == 'project_data']
    assert len(project_events) >= 1
    data = project_events[0]['args'][0]
    assert data['is_pristine'] is False
    ws.disconnect()
