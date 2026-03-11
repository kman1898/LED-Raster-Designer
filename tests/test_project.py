"""Tests for project management API endpoints."""

import json


def test_get_project_returns_default(client):
    """GET /api/project returns the default empty project."""
    resp = client.get('/api/project')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['name'] == 'Untitled Project'
    assert data['raster_width'] == 1920
    assert data['raster_height'] == 1080
    assert isinstance(data['layers'], list)


def test_new_project_resets_state(client_with_layer):
    """POST /api/project/new resets project and adds a default layer."""
    resp = client_with_layer.post('/api/project/new')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['name'] == 'Untitled Project'
    assert data['raster_width'] == 1920
    # New project gets a default layer
    assert len(data['layers']) == 1
    assert data['layers'][0]['name'] == 'Screen1'


def test_save_project(client):
    """POST /api/project saves project data."""
    resp = client.post('/api/project', json={
        'name': 'My LED Wall',
        'raster_width': 3840,
        'raster_height': 2160,
    })
    assert resp.status_code == 200

    # Verify it persists
    resp = client.get('/api/project')
    data = resp.get_json()
    assert data['name'] == 'My LED Wall'
    assert data['raster_width'] == 3840


def test_restore_project(client):
    """PUT /api/project restores entire project state."""
    project_data = {
        'name': 'Restored Project',
        'raster_width': 2560,
        'raster_height': 1440,
        'layers': []
    }
    resp = client.put('/api/project', json=project_data)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['name'] == 'Restored Project'
    assert data['raster_width'] == 2560


def test_server_session(client):
    """GET /api/server-session returns session ID and start time."""
    resp = client.get('/api/server-session')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'session_id' in data
    assert 'start_time' in data
    assert isinstance(data['start_time'], int)
