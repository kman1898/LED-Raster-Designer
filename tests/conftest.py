"""Shared pytest fixtures for LED Raster Designer tests."""

import sys
import os
import pytest

# Add src/ to path so we can import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app import app, socketio, current_project, initialize_default_layer


@pytest.fixture()
def client():
    """Create a Flask test client with a fresh project state."""
    app.config['TESTING'] = True

    # Reset project state before each test
    current_project.clear()
    current_project.update({
        'name': 'Untitled Project',
        'raster_width': 1920,
        'raster_height': 1080,
        'layers': []
    })

    with app.test_client() as client:
        yield client


@pytest.fixture()
def client_with_layer(client):
    """Create a test client with one default layer already added."""
    resp = client.post('/api/layer/add', json={
        'name': 'TestScreen',
        'columns': 4,
        'rows': 3,
        'cabinet_width': 128,
        'cabinet_height': 128,
    })
    assert resp.status_code == 200
    return client
