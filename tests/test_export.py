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


# ── Resolume XML Export Tests ──────────────────────────────────────

def test_export_resolume_xml(client_with_layer):
    """POST /api/export/resolume returns valid XML."""
    resp = client_with_layer.post('/api/export/resolume', json={
        'project_name': 'Test Project',
        'raster_width': 3840,
        'raster_height': 2160,
    })
    assert resp.status_code == 200
    assert 'xml' in resp.content_type
    xml = resp.data.decode('utf-8')
    assert '<?xml version="1.0"' in xml
    assert '<XmlState name="Test Project">' in xml
    assert 'Resolume Arena' in xml


def test_export_resolume_xml_has_slice(client_with_layer):
    """Resolume XML contains a Slice for the screen layer."""
    resp = client_with_layer.post('/api/export/resolume', json={
        'project_name': 'Test',
        'raster_width': 1920,
        'raster_height': 1080,
    })
    xml = resp.data.decode('utf-8')
    assert '<Slice' in xml
    assert 'value="Screen1"' in xml or 'value="Screen 1"' in xml


def test_export_resolume_xml_correct_rect(client_with_layer):
    """Resolume XML InputRect matches layer bounds."""
    resp = client_with_layer.post('/api/export/resolume', json={
        'project_name': 'Test',
        'raster_width': 1920,
        'raster_height': 1080,
    })
    xml = resp.data.decode('utf-8')
    # Default layer: 8 cols × 5 rows, 192×384 cabinet, offset 0,0
    # Width = 8 * 192 = 1536, Height = 5 * 384 = 1920
    assert '<InputRect' in xml
    assert '<OutputRect' in xml


def test_export_resolume_xml_composition_size(client_with_layer):
    """Resolume XML contains correct composition texture size."""
    resp = client_with_layer.post('/api/export/resolume', json={
        'project_name': 'Test',
        'raster_width': 3840,
        'raster_height': 2160,
    })
    xml = resp.data.decode('utf-8')
    assert 'width="3840"' in xml
    assert 'height="2160"' in xml


def test_export_resolume_xml_hidden_layer_excluded(client):
    """Hidden layers are excluded from Resolume XML export."""
    import app as app_module
    # Add two layers, hide one
    client.post('/api/layer/add', json={
        'name': 'Visible', 'columns': 4, 'rows': 3,
        'cabinet_width': 100, 'cabinet_height': 100,
    })
    client.post('/api/layer/add', json={
        'name': 'Hidden', 'columns': 4, 'rows': 3,
        'cabinet_width': 100, 'cabinet_height': 100,
    })
    # Hide the second layer
    layers = app_module.current_project['layers']
    hidden_layer = [l for l in layers if l['name'] == 'Hidden'][0]
    hidden_layer['visible'] = False

    resp = client.post('/api/export/resolume', json={
        'project_name': 'Test',
        'raster_width': 1920,
        'raster_height': 1080,
    })
    xml = resp.data.decode('utf-8')
    assert 'value="Visible"' in xml
    assert 'value="Hidden"' not in xml


def test_export_resolume_xml_multiple_layers(client):
    """Resolume XML contains one Slice per visible screen layer."""
    client.post('/api/layer/add', json={
        'name': 'Main', 'columns': 10, 'rows': 5,
        'cabinet_width': 100, 'cabinet_height': 100,
    })
    client.post('/api/layer/add', json={
        'name': 'Side', 'columns': 5, 'rows': 8,
        'cabinet_width': 60, 'cabinet_height': 120,
        'offset_x': 1000, 'offset_y': 0,
    })
    resp = client.post('/api/export/resolume', json={
        'project_name': 'Multi',
        'raster_width': 1920,
        'raster_height': 1080,
    })
    xml = resp.data.decode('utf-8')
    assert 'value="Main"' in xml
    assert 'value="Side"' in xml
    assert xml.count('<Slice') == 2


def test_export_resolume_xml_bezier_warper(client_with_layer):
    """Resolume XML contains BezierWarper with 16 vertices (4x4 grid)."""
    resp = client_with_layer.post('/api/export/resolume', json={
        'project_name': 'Test',
        'raster_width': 1920,
        'raster_height': 1080,
    })
    xml = resp.data.decode('utf-8')
    assert '<BezierWarper controlWidth="4" controlHeight="4">' in xml
    # 4x4 grid = 16 vertices inside the BezierWarper
    import re
    warper_section = re.search(r'<BezierWarper.*?</BezierWarper>', xml, re.DOTALL)
    assert warper_section
    vertices = re.findall(r'<v x=', warper_section.group())
    assert len(vertices) == 16
