"""Tests for WebSocket events, connect, disconnect, and broadcasts."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app import app, socketio
import app as app_module


@pytest.fixture()
def socketio_client():
    """Create a Flask-SocketIO test client."""
    app.config['TESTING'] = True
    app_module.current_project = {
        'name': 'Untitled Project',
        'raster_width': 1920,
        'raster_height': 1080,
        'layers': [],
        'is_pristine': True
    }
    app_module.next_layer_id = 1
    client = socketio.test_client(app)
    yield client
    client.disconnect()


def test_connect_sends_project_data(socketio_client):
    """On connect, server emits project_data with current project."""
    assert socketio_client.is_connected()
    received = socketio_client.get_received()
    # Should have received project_data event
    project_events = [r for r in received if r['name'] == 'project_data']
    assert len(project_events) >= 1
    data = project_events[0]['args'][0]
    assert data['name'] == 'Untitled Project'
    assert data['raster_width'] == 1920


def test_layer_add_emits_event(socketio_client):
    """Adding a layer emits layer_added via WebSocket."""
    # Clear initial events
    socketio_client.get_received()

    # Add layer via HTTP
    http_client = app.test_client()
    resp = http_client.post('/api/layer/add', json={
        'name': 'WSTest',
        'columns': 2,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 100,
    })
    assert resp.status_code == 200

    received = socketio_client.get_received()
    layer_events = [r for r in received if r['name'] == 'layer_added']
    assert len(layer_events) >= 1
    assert layer_events[0]['args'][0]['name'] == 'WSTest'


def test_layer_update_emits_event(socketio_client):
    """Updating a layer emits layer_updated via WebSocket."""
    http_client = app.test_client()
    resp = http_client.post('/api/layer/add', json={
        'name': 'UpdateWS',
        'columns': 2,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 100,
    })
    layer_id = resp.get_json()['id']

    # Clear events
    socketio_client.get_received()

    # Update layer
    http_client.put(f'/api/layer/{layer_id}', json={'name': 'Updated'})

    received = socketio_client.get_received()
    update_events = [r for r in received if r['name'] == 'layer_updated']
    assert len(update_events) >= 1


def test_layer_delete_emits_event(socketio_client):
    """Deleting a layer emits layer_deleted via WebSocket."""
    http_client = app.test_client()
    resp = http_client.post('/api/layer/add', json={
        'name': 'DeleteWS',
        'columns': 2,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 100,
    })
    layer_id = resp.get_json()['id']

    # Clear events
    socketio_client.get_received()

    # Delete layer
    http_client.delete(f'/api/layer/{layer_id}')

    received = socketio_client.get_received()
    delete_events = [r for r in received if r['name'] == 'layer_deleted']
    assert len(delete_events) >= 1


def test_panel_toggle_emits_event(socketio_client):
    """Toggling a panel emits panel_updated via WebSocket."""
    http_client = app.test_client()
    resp = http_client.post('/api/layer/add', json={
        'name': 'PanelWS',
        'columns': 2,
        'rows': 2,
        'cabinet_width': 100,
        'cabinet_height': 100,
    })
    layer = resp.get_json()
    layer_id = layer['id']
    panel_id = layer['panels'][0]['id']

    # Clear events
    socketio_client.get_received()

    # Toggle panel
    http_client.post(f'/api/layer/{layer_id}/panel/{panel_id}/toggle')

    received = socketio_client.get_received()
    panel_events = [r for r in received if r['name'] == 'panel_updated']
    assert len(panel_events) >= 1


def test_project_restore_emits_event(socketio_client):
    """Restoring a project emits project_updated via WebSocket."""
    # Clear events
    socketio_client.get_received()

    http_client = app.test_client()
    http_client.put('/api/project', json={
        'name': 'Restored',
        'raster_width': 800,
        'raster_height': 600,
        'layers': [],
    })

    received = socketio_client.get_received()
    project_events = [r for r in received if r['name'] == 'project_updated']
    assert len(project_events) >= 1


def test_new_project_emits_cleared(socketio_client):
    """Creating a new project emits project_cleared via WebSocket."""
    # Clear events
    socketio_client.get_received()

    http_client = app.test_client()
    http_client.post('/api/project/new')

    received = socketio_client.get_received()
    cleared_events = [r for r in received if r['name'] == 'project_cleared']
    assert len(cleared_events) >= 1
