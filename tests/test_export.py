"""Tests for export API endpoints."""

import io
import json
import zipfile
import base64


def _make_test_image_data():
    """Create a minimal valid base64 PNG for testing."""
    from PIL import Image
    img = Image.new('RGBA', (10, 10), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'data:image/png;base64,{b64}'


def test_export_png(client_with_layer):
    """POST /api/export/png returns a PNG image."""
    resp = client_with_layer.post('/api/export/png', json={
        'include_borders': True,
    })
    assert resp.status_code == 200
    assert resp.content_type == 'image/png'
    # PNG magic bytes
    assert resp.data[:4] == b'\x89PNG'


def test_export_psd(client_with_layer):
    """POST /api/export/psd returns a PSD file (or ZIP fallback without pytoshop)."""
    resp = client_with_layer.post('/api/export/psd', json={
        'include_borders': True,
    })
    assert resp.status_code == 200
    # PSD magic bytes "8BPS" if pytoshop installed, ZIP "PK" as fallback
    assert resp.data[:4] in (b'8BPS', b'PK\x03\x04')


def test_export_unified_single_png(client_with_layer):
    """POST /api/export with format=png and one view returns PNG."""
    resp = client_with_layer.post('/api/export', json={
        'format': 'png',
        'views': ['pixel-map'],
        'project_name': 'Test',
    })
    assert resp.status_code == 200
    assert resp.data[:4] == b'\x89PNG'


def test_export_unified_multi_png_zip(client_with_layer):
    """POST /api/export with format=png and multiple views returns ZIP."""
    resp = client_with_layer.post('/api/export', json={
        'format': 'png',
        'views': ['pixel-map', 'cabinet-id'],
        'project_name': 'Test',
    })
    assert resp.status_code == 200
    assert resp.content_type == 'application/zip'
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert len(zf.namelist()) == 2


def test_export_unified_pdf(client_with_layer):
    """POST /api/export with format=pdf returns a PDF."""
    resp = client_with_layer.post('/api/export', json={
        'format': 'pdf',
        'views': ['pixel-map'],
        'project_name': 'Test',
    })
    assert resp.status_code == 200
    assert resp.data[:5] == b'%PDF-'


def test_export_zip_images(client_with_layer):
    """POST /api/export/zip-images creates a ZIP from base64 images."""
    img_data = _make_test_image_data()
    resp = client_with_layer.post('/api/export/zip-images', json={
        'project_name': 'Test',
        'images': [
            {'name': 'view1.png', 'data': img_data},
            {'name': 'view2.png', 'data': img_data},
        ],
    })
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert 'view1.png' in zf.namelist()
    assert 'view2.png' in zf.namelist()


def test_export_pdf_from_images(client_with_layer):
    """POST /api/export/pdf-from-images creates a PDF from base64 images."""
    img_data = _make_test_image_data()
    resp = client_with_layer.post('/api/export/pdf-from-images', json={
        'project_name': 'Test',
        'images': [
            {'name': 'Pixel Map', 'data': img_data, 'width': 100, 'height': 100},
        ],
    })
    assert resp.status_code == 200
    assert resp.data[:5] == b'%PDF-'


def test_export_zip_layers(client_with_layer):
    """POST /api/export/zip returns ZIP of layer PNGs with manifest."""
    resp = client_with_layer.post('/api/export/zip', json={
        'include_borders': True,
    })
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert 'manifest.json' in zf.namelist()


def test_client_log(client):
    """POST /api/log accepts client-side log entries."""
    resp = client.post('/api/log', json={
        'action': 'test_action',
        'details': {'key': 'value'},
    })
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'ok'
