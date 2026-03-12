"""Advanced export tests: PSD from client images, multi-page PDF, edge cases."""

import io
import json
import zipfile
import base64
import pytest
from PIL import Image

# Check if pytoshop is available (not installed in all test environments)
try:
    import pytoshop
    HAS_PYTOSHOP = True
except ImportError:
    HAS_PYTOSHOP = False


def _make_test_image_data(width=100, height=100, color=(255, 0, 0, 255)):
    """Create a valid base64 PNG data URL for testing."""
    img = Image.new('RGBA', (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'data:image/png;base64,{b64}'


# ── PSD from single client image ────────────────────────────────────

@pytest.mark.skipif(not HAS_PYTOSHOP, reason="pytoshop not installed")
def test_export_psd_from_image(client_with_layer):
    """POST /api/export/psd-from-image creates a PSD with screen layers."""
    img_data = _make_test_image_data(1920, 1080)
    project = client_with_layer.get('/api/project').get_json()
    layer = project['layers'][0]

    resp = client_with_layer.post('/api/export/psd-from-image', json={
        'project_name': 'Test',
        'view_name': 'Pixel Map',
        'image_data': img_data,
        'width': 1920,
        'height': 1080,
        'layers': [{
            'name': layer['name'],
            'offset_x': layer.get('offset_x', 0),
            'offset_y': layer.get('offset_y', 0),
            'width': layer['columns'] * layer['cabinet_width'],
            'height': layer['rows'] * layer['cabinet_height'],
            'visible': True,
        }],
    })
    assert resp.status_code == 200
    # PSD magic bytes "8BPS"
    assert resp.data[:4] == b'8BPS'


def test_export_psd_from_image_without_pytoshop(client_with_layer):
    """PSD-from-image returns 500 with error message when pytoshop missing."""
    if HAS_PYTOSHOP:
        pytest.skip("pytoshop is installed; testing missing-library path not possible")
    img_data = _make_test_image_data(200, 200)
    resp = client_with_layer.post('/api/export/psd-from-image', json={
        'project_name': 'Test',
        'view_name': 'Test',
        'image_data': img_data,
        'width': 200,
        'height': 200,
        'layers': [],
    })
    assert resp.status_code == 500
    data = resp.get_json()
    assert 'error' in data
    assert 'pytoshop' in data['error'].lower()


@pytest.mark.skipif(not HAS_PYTOSHOP, reason="pytoshop not installed")
def test_export_psd_from_image_no_layers(client_with_layer):
    """PSD from image with empty layers list still succeeds."""
    img_data = _make_test_image_data(200, 200)
    resp = client_with_layer.post('/api/export/psd-from-image', json={
        'project_name': 'Empty',
        'view_name': 'Test',
        'image_data': img_data,
        'width': 200,
        'height': 200,
        'layers': [],
    })
    assert resp.status_code == 200
    assert resp.data[:4] == b'8BPS'


@pytest.mark.skipif(not HAS_PYTOSHOP, reason="pytoshop not installed")
def test_export_psd_from_image_hidden_layer(client_with_layer):
    """Invisible layers are skipped in PSD output."""
    img_data = _make_test_image_data(200, 200)
    resp = client_with_layer.post('/api/export/psd-from-image', json={
        'project_name': 'HiddenTest',
        'view_name': 'Test',
        'image_data': img_data,
        'width': 200,
        'height': 200,
        'layers': [{
            'name': 'Hidden',
            'offset_x': 0, 'offset_y': 0,
            'width': 100, 'height': 100,
            'visible': False,
        }],
    })
    assert resp.status_code == 200
    assert resp.data[:4] == b'8BPS'


# ── PSD ZIP from multiple client images ─────────────────────────────

@pytest.mark.skipif(not HAS_PYTOSHOP, reason="pytoshop not installed")
def test_export_psd_zip_from_images(client_with_layer):
    """POST /api/export/psd-zip-from-images creates ZIP of PSDs."""
    img_data = _make_test_image_data(200, 200)
    resp = client_with_layer.post('/api/export/psd-zip-from-images', json={
        'project_name': 'MultiView',
        'width': 200,
        'height': 200,
        'images': [
            {'name': 'Pixel Map', 'data': img_data},
            {'name': 'Cabinet ID', 'data': img_data},
        ],
        'layers': [{
            'name': 'Screen1',
            'offset_x': 0, 'offset_y': 0,
            'width': 100, 'height': 100,
            'visible': True,
        }],
    })
    assert resp.status_code == 200
    assert resp.content_type == 'application/zip'
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    names = zf.namelist()
    assert len(names) == 2
    # Each file should be a valid PSD
    for name in names:
        assert name.endswith('.psd')
        psd_data = zf.read(name)
        assert psd_data[:4] == b'8BPS'


def test_export_psd_zip_without_pytoshop(client_with_layer):
    """PSD-ZIP returns 500 with error when pytoshop missing."""
    if HAS_PYTOSHOP:
        pytest.skip("pytoshop is installed")
    img_data = _make_test_image_data(100, 100)
    resp = client_with_layer.post('/api/export/psd-zip-from-images', json={
        'project_name': 'Test',
        'width': 100,
        'height': 100,
        'images': [{'name': 'View', 'data': img_data}],
        'layers': [],
    })
    assert resp.status_code == 500
    assert 'error' in resp.get_json()


# ── Export with empty project ───────────────────────────────────────

def test_export_png_empty_project(client):
    """Exporting PNG with no layers produces a black image."""
    resp = client.post('/api/export/png', json={'include_borders': True})
    assert resp.status_code == 200
    assert resp.data[:4] == b'\x89PNG'


def test_export_zip_empty_project(client):
    """Exporting ZIP with no layers still returns a valid ZIP with manifest."""
    resp = client.post('/api/export/zip', json={'include_borders': True})
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert 'manifest.json' in zf.namelist()
    manifest = json.loads(zf.read('manifest.json'))
    assert manifest['layers'] == []


# ── Unified export additional cases ─────────────────────────────────

@pytest.mark.skipif(not HAS_PYTOSHOP, reason="pytoshop not installed")
def test_export_unified_psd_single_view(client_with_layer):
    """POST /api/export with format=psd and one view returns PSD."""
    resp = client_with_layer.post('/api/export', json={
        'format': 'psd',
        'views': ['pixel-map'],
        'project_name': 'Test',
    })
    assert resp.status_code == 200
    # PSD or ZIP fallback
    assert resp.data[:4] in (b'8BPS', b'PK\x03\x04')


def test_export_unified_psd_without_pytoshop(client_with_layer):
    """Unified PSD export returns 500 when pytoshop missing."""
    if HAS_PYTOSHOP:
        pytest.skip("pytoshop is installed")
    resp = client_with_layer.post('/api/export', json={
        'format': 'psd',
        'views': ['pixel-map'],
        'project_name': 'Test',
    })
    assert resp.status_code == 500
    assert 'error' in resp.get_json()


def test_export_unified_multi_pdf(client_with_layer):
    """POST /api/export with format=pdf and multiple views returns multi-page PDF."""
    resp = client_with_layer.post('/api/export', json={
        'format': 'pdf',
        'views': ['pixel-map', 'cabinet-id'],
        'project_name': 'Test',
    })
    assert resp.status_code == 200
    assert resp.data[:5] == b'%PDF-'


# ── Multi-page PDF from images ──────────────────────────────────────

def test_export_pdf_multiple_images(client):
    """PDF export with multiple images creates multi-page document."""
    img_data = _make_test_image_data(100, 100)
    resp = client.post('/api/export/pdf-from-images', json={
        'project_name': 'MultiPage',
        'images': [
            {'name': 'Page 1', 'data': img_data, 'width': 100, 'height': 100},
            {'name': 'Page 2', 'data': img_data, 'width': 100, 'height': 100},
            {'name': 'Page 3', 'data': img_data, 'width': 100, 'height': 100},
        ],
    })
    assert resp.status_code == 200
    assert resp.data[:5] == b'%PDF-'


# ── Export with blank/hidden panels ─────────────────────────────────

def test_export_png_with_blank_panels(client_with_layer):
    """PNG export works correctly when panels are blanked."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']
    panel_id = project['layers'][0]['panels'][0]['id']

    # Blank a panel
    client_with_layer.post(f'/api/layer/{layer_id}/panel/{panel_id}/toggle')

    resp = client_with_layer.post('/api/export/png', json={'include_borders': True})
    assert resp.status_code == 200
    assert resp.data[:4] == b'\x89PNG'


def test_export_png_with_hidden_panels(client_with_layer):
    """PNG export works correctly when panels are hidden."""
    project = client_with_layer.get('/api/project').get_json()
    layer_id = project['layers'][0]['id']
    panel_id = project['layers'][0]['panels'][0]['id']

    # Hide a panel
    client_with_layer.post(f'/api/layer/{layer_id}/panel/{panel_id}/toggle_hidden')

    resp = client_with_layer.post('/api/export/png', json={'include_borders': True})
    assert resp.status_code == 200
    assert resp.data[:4] == b'\x89PNG'


def test_export_png_no_borders(client_with_layer):
    """PNG export without borders flag."""
    resp = client_with_layer.post('/api/export/png', json={'include_borders': False})
    assert resp.status_code == 200
    assert resp.data[:4] == b'\x89PNG'
